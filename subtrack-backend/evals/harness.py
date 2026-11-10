"""Run one eval question through the real assistant loop against seeded data.

Pass ``model`` to replace Claude with a scripted stand-in (offline evals). Leave
it out to call Claude itself (live evals).
"""
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import (
    AgentAction,
    AgentMessage,
    AgentThread,
    BillingCycle,
    Category,
    PaymentReminder,
    SafeToSpendProfile,
    Subscription,
    Transaction,
    UserPreference,
)
from app.routers import agent as agent_router
from evals.graders import ToolCall, Transcript

EVAL_USER = "eval-user"
CASES_PATH = Path(__file__).with_name("cases.json")
RATES = {"rates": {"USD": 0.65}, "stale": False, "fetched_at": "2026-11-01T00:00:00"}
PAYMENTS = [
    ("Rent", "400.00", 3),
    ("Netflix", "22.99", 5),
    ("Phone plan", "35.00", 7),
    ("Spotify", "13.99", 12),
]


def load_cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text())


def seed(db: Session, now: datetime) -> None:
    """A user with $900, payday in 9 days, a $50 buffer and four payments."""
    db.add(UserPreference(user_id=EVAL_USER, base_currency="AUD", timezone="UTC"))
    db.add(SafeToSpendProfile(
        user_id=EVAL_USER,
        balance=Decimal("900.00"),
        currency="AUD",
        balance_as_of=now,
        pay_anchor_on=(now + timedelta(days=9)).date(),
        pay_interval_unit="week",
        pay_interval_count=2,
        buffer=Decimal("50.00"),
    ))
    for name, amount, due_in_days in PAYMENTS:
        db.add(Subscription(
            user_id=EVAL_USER,
            name=name,
            category=list(Category)[0],
            amount=float(amount),
            currency="AUD",
            cycle=BillingCycle.monthly,
            interval_unit="month",
            interval_count=1,
            next_due=now + timedelta(days=due_in_days),
        ))
    db.commit()


def _snapshot(db: Session) -> str:
    db.expire_all()
    rows = [
        (row.name, row.amount, row.status, str(row.next_due))
        for row in db.query(Subscription).filter_by(user_id=EVAL_USER).order_by(Subscription.name)
    ]
    reminders = db.query(PaymentReminder).filter_by(user_id=EVAL_USER).count()
    transactions = db.query(Transaction).filter_by(user_id=EVAL_USER).count()
    return json.dumps([rows, reminders, transactions], default=str)


def run_case(db: Session, question: str, model: Callable[..., object] | None = None) -> Transcript:
    thread = AgentThread(id=uuid4(), user_id=EVAL_USER, title="Eval", next_message_sequence=2)
    asked = AgentMessage(
        id=uuid4(), thread_id=thread.id, user_id=EVAL_USER,
        role="user", sequence=1, content=question, status="completed",
    )
    reply = AgentMessage(
        id=uuid4(), thread_id=thread.id, user_id=EVAL_USER, role="assistant",
        sequence=2, content="", status="streaming", reply_to_id=asked.id,
    )
    db.add_all([thread, asked, reply])
    db.commit()
    thread_id, reply_id = thread.id, reply.id
    before = _snapshot(db)
    calls: list[ToolCall] = []
    real_run_tool = agent_router.run_tool

    def recording_run_tool(name, tool_input, *args, **kwargs):
        result = real_run_tool(name, tool_input, *args, **kwargs)
        calls.append(ToolCall(name, tool_input, result))
        return result

    patches = [
        patch.object(agent_router, "run_tool", side_effect=recording_run_tool),
        patch.object(agent_router, "record_call"),
        patch("app.agent.finance.get_cached_rate_snapshot", return_value=RATES),
    ]
    if model is not None:
        patches.append(patch.object(agent_router.client.messages, "stream", side_effect=model))
    for active in patches:
        active.start()
    try:
        for _ in agent_router._stream_reply(db, thread_id, reply_id, EVAL_USER):
            pass
    finally:
        for active in reversed(patches):
            active.stop()

    # Some tools detach every loaded row (the duplicate check releases its
    # connection before calling the model), so look the reply up again.
    reply = db.get(AgentMessage, reply_id)
    if reply.status != "completed":
        raise RuntimeError(f"assistant reply failed: {reply.error_code}")
    resolved = db.query(AgentAction).filter(
        AgentAction.user_id == EVAL_USER, AgentAction.status != "pending"
    ).count()
    return Transcript(
        question=question,
        answer=reply.content,
        tool_calls=calls,
        data_changed=before != _snapshot(db) or resolved > 0,
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
