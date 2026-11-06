"""Record latency, tokens and cost for every Claude API call.

Traces are deliberately anonymous: no user ID, prompt, reply or tool input is
stored, so they never hold financial data and need no export or deletion.
Recording is best effort and never fails the request it measures.
"""
import logging
import time
from collections.abc import Callable, Iterable
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import AiCallTrace

logger = logging.getLogger(__name__)

MILLION = Decimal(1_000_000)
# USD per million tokens. Check against Anthropic's pricing page when changing models.
MODEL_PRICES = {
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


def traced_call(feature: str, call: Callable[..., Any], **kwargs: Any) -> Any:
    """Run one Claude API call and record it, including calls that raise."""
    started = time.perf_counter()
    try:
        response = call(**kwargs)
    except Exception as exc:
        record_call(feature, kwargs["model"], None, elapsed_ms(started), error_code=type(exc).__name__)
        raise
    record_call(feature, kwargs["model"], response, elapsed_ms(started))
    return response

