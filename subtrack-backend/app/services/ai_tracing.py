"""Record latency, tokens and cost for every Claude API call.

Traces are deliberately anonymous: no user ID, prompt, reply or tool input is
stored, so they never hold financial data and need no export or deletion.
Recording is best effort and never fails the request it measures.
"""
import logging
import math
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import AiCallTrace

logger = logging.getLogger(__name__)

MILLION = Decimal(1_000_000)
# USD per million tokens. Check against Anthropic's pricing page when changing models.
MODEL_PRICES = {
    # Prompts over 100K tokens cost 5x more; Subtrack's prompts stay well below that.
    "claude-haiku-5-5": {
        "input": Decimal("0.10"),
        "output": Decimal("0.50"),
        "cache_write": Decimal("0.125"),
        "cache_read": Decimal("0.01"),
    },
    "claude-haiku-4-5": {
        "input": Decimal("1.00"),
        "output": Decimal("5.00"),
        "cache_write": Decimal("1.25"),
        "cache_read": Decimal("0.10"),
    },
}
WEB_SEARCH_PRICE = Decimal("0.01")


def elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _count(usage: Any, field: str) -> int:
    value = getattr(usage, field, None)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def call_cost(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
    web_searches: int,
) -> Decimal:
    """Cost of one call in USD. Unknown models cost 0 and log a warning."""
    prices = MODEL_PRICES.get(model)
    if prices is None:
        logger.warning("No price for model %s; recording zero cost", model)
        return Decimal(0)
    tokens = (
        input_tokens * prices["input"]
        + output_tokens * prices["output"]
        + cache_read_tokens * prices["cache_read"]
        + cache_write_tokens * prices["cache_write"]
    )
    return tokens / MILLION + web_searches * WEB_SEARCH_PRICE


def record_call(
    feature: str,
    model: str,
    response: Any | None,
    latency_ms: int,
    *,
    run_id: UUID | None = None,
    step: int | None = None,
    tool_names: Iterable[str] | None = None,
    tool_ms: int | None = None,
    error_code: str | None = None,
) -> None:
    usage = getattr(response, "usage", None)
    server_tools = getattr(usage, "server_tool_use", None)
    stop_reason = getattr(response, "stop_reason", None)
    counts = {
        "input_tokens": _count(usage, "input_tokens"),
        "output_tokens": _count(usage, "output_tokens"),
        "cache_read_tokens": _count(usage, "cache_read_input_tokens"),
        "cache_write_tokens": _count(usage, "cache_creation_input_tokens"),
        "web_searches": _count(server_tools, "web_search_requests"),
    }
    trace = AiCallTrace(
        feature=feature,
        model=model,
        run_id=run_id,
        step=step,
        latency_ms=latency_ms,
        cost_usd=call_cost(model, **counts),
        stop_reason=stop_reason if isinstance(stop_reason, str) else None,
        tool_names=list(tool_names) if tool_names else None,
        tool_ms=tool_ms,
        error_code=error_code,
        **counts,
    )
    db = SessionLocal()
    try:
        db.add(trace)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Could not record AI call trace (%s)", type(exc).__name__)
    finally:
        db.close()


# Today's spend is re-read at most this often per process.
SPEND_CACHE_SECONDS = 60
_spend_cache: dict[str, tuple[float, Decimal]] = {}
_spend_cache_lock = threading.Lock()


class AiBudgetExceeded(HTTPException):
    """Today's total AI spend has reached AI_DAILY_COST_LIMIT_USD."""

    def __init__(self) -> None:
        super().__init__(
            status_code=503,
            detail="AI features are paused for today. Everything else still works.",
        )


def _spent_today_usd() -> Decimal:
    """Total recorded AI cost since UTC midnight, cached briefly."""
    today = datetime.now(timezone.utc).replace(tzinfo=None).date()
    now = time.monotonic()
    with _spend_cache_lock:
        cached = _spend_cache.get(today.isoformat())
        if cached and now - cached[0] < SPEND_CACHE_SECONDS:
            return cached[1]
    db = SessionLocal()
    try:
        spent = db.query(func.coalesce(func.sum(AiCallTrace.cost_usd), 0)).filter(
            AiCallTrace.created_at >= datetime.combine(today, datetime.min.time())
        ).scalar()
    finally:
        db.close()
    spent = Decimal(str(spent or 0))
    with _spend_cache_lock:
        _spend_cache.clear()
        _spend_cache[today.isoformat()] = (now, spent)
    return spent


def require_ai_budget() -> None:
    """Raise AiBudgetExceeded once today's spend reaches the configured limit.

    A limit of 0 disables the check. If the spend can't be read, AI stays on:
    the breaker guards cost, and must not take features down on its own.
    """
    limit = settings.ai_daily_cost_limit_usd
    if limit <= 0:
        return
    try:
        spent = _spent_today_usd()
    except SQLAlchemyError as exc:
        logger.warning("Could not read today's AI spend (%s)", type(exc).__name__)
        return
    if spent >= Decimal(str(limit)):
        raise AiBudgetExceeded()


def traced_call(feature: str, call: Callable[..., Any], **kwargs: Any) -> Any:
    """Run one Claude API call and record it, including calls that raise."""
    require_ai_budget()
    started = time.perf_counter()
    try:
        response = call(**kwargs)
    except Exception as exc:
        record_call(feature, kwargs["model"], None, elapsed_ms(started), error_code=type(exc).__name__)
        raise
    record_call(feature, kwargs["model"], response, elapsed_ms(started))
    return response


def _percentile(values: list[int], fraction: float) -> int | None:
    """Nearest-rank percentile; None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def usage_summary(db: Session, since: datetime) -> dict[str, dict]:
    """Per-feature call count, error rate, latency percentiles and cost since a time.

    For the assistant, latency and cost are also reported per request, since
    one request can make several model calls.
    """
    traces = db.query(AiCallTrace).filter(AiCallTrace.created_at >= since).all()
    by_feature: dict[str, list[AiCallTrace]] = defaultdict(list)
    for trace in traces:
        by_feature[trace.feature].append(trace)

    summary = {}
    for feature, rows in sorted(by_feature.items()):
        latencies = [row.latency_ms for row in rows]
        cost = sum((row.cost_usd for row in rows), Decimal(0))
        entry = {
            "calls": len(rows),
            "error_rate": sum(1 for row in rows if row.error_code) / len(rows),
            "p50_ms": _percentile(latencies, 0.5),
            "p95_ms": _percentile(latencies, 0.95),
            "cost_usd": cost,
        }
        runs: dict[UUID, list[AiCallTrace]] = defaultdict(list)
        for row in rows:
            if row.run_id is not None:
                runs[row.run_id].append(row)
        if runs:
            request_ms = [
                sum(row.latency_ms + (row.tool_ms or 0) for row in steps)
                for steps in runs.values()
            ]
            entry.update(
                requests=len(runs),
                request_p50_ms=_percentile(request_ms, 0.5),
                request_p95_ms=_percentile(request_ms, 0.95),
                cost_per_request_usd=sum(
                    (row.cost_usd for steps in runs.values() for row in steps), Decimal(0)
                ) / len(runs),
            )
        summary[feature] = entry
    return summary
