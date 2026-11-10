"""Live data for each block on a workspace page.

Every resolver reads through the same services the Spending, Payments, Budgets
and Goals screens use, so a block always shows the numbers those screens show.
A block that fails returns an error for itself only; the rest of the page loads.
Amounts without a valid conversion are counted and reported, never taken 1:1.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from datetime import date, datetime
from decimal import ROUND_DOWN, Decimal
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.agent.finance import CurrencyContext
from app.models import Goal, Subscription, TransactionKind
from app.routers.goals import list_goals
from app.routers.rates import get_cached_rate_snapshot
from app.routers.subscriptions import get_subscriptions, get_upcoming_forecast
from app.routers.transactions import transaction_payload
from app.services.budgets import _add_logged_expenses, _add_tracked_payments, _CategorySpend, budget_status
from app.services.safe_to_spend import _user_zone
from app.services.transactions import (
    CENTS,
    MONTH_ROW_LIMIT,
    amount_in_base,
    base_currency_for,
    month_transactions,
)
from app.services.workspace_blocks import (
    Block,
    BudgetBlock,
    ChecklistBlock,
    GoalProgressBlock,
    NotesBlock,
    PaymentListBlock,
    SharedCostsBlock,
    SpendingTrendBlock,
    TransactionLogBlock,
    UpcomingPaymentsBlock,
)

logger = logging.getLogger(__name__)

BLOCK_FAILED = "This block could not be loaded."
TRANSACTION_LOG_LIMIT = 100
RANGE_MONTHS = {"this_month": (0,), "last_month": (1,), "last_3_months": (0, 1, 2)}
ZERO = Decimal("0")

block_adapter: TypeAdapter[Block] = TypeAdapter(Block)


def _money(value: Decimal) -> float:
    return float(value.quantize(CENTS))


def _months_back(today: date, offset: int) -> tuple[int, int]:
    index = today.year * 12 + today.month - 1 - offset
    return index // 12, index % 12 + 1


def _existing_ids(db: Session, user_id: str, model: type, ids: list[UUID] | None) -> set[str]:
    if not ids:
        return set()
    return {str(row_id) for (row_id,) in db.query(model.id).filter(model.user_id == user_id, model.id.in_(set(ids)))}


def _missing_count(db: Session, user_id: str, model: type, ids: list[UUID] | None) -> int:
    return len(set(ids or ())) - len(_existing_ids(db, user_id, model, ids))


def payment_list(db: Session, user_id: str, block: PaymentListBlock, today: date) -> dict:
    """Active payments with their monthly cost in the base currency.

    Listed payments that were deleted count in ``missing_count``; listed ones
    that still exist but are cancelled or ended count in ``inactive_count``.
    """
    currency = CurrencyContext.for_user(db, user_id)
    wanted = {str(payment_id) for payment_id in block.payment_ids} if block.payment_ids else None
    active = get_subscriptions(include_inactive=False, user_id=user_id, db=db)
    existing = _existing_ids(db, user_id, Subscription, block.payment_ids)
    rows = []
    qualities = []
    monthly_total = 0.0
    unconverted = 0
    for payment in active:
        if wanted is not None and payment["id"] not in wanted:
            continue
        if block.category is not None and payment["category"] != block.category.value:
            continue
        monthly_in_base, quality = currency.convert(payment["monthly_equivalent"], payment["currency"])
        qualities.append(quality)
        if monthly_in_base is None:
            unconverted += 1
        else:
            monthly_total += monthly_in_base
        rows.append({
            "id": payment["id"],
            "name": payment["name"],
            "category": payment["category"],
            "amount": payment["amount"],
            "currency": payment["currency"],
            "cadence_label": payment["cadence_label"],
            "next_due": payment["next_expected_at"],
            "monthly_in_base": None if monthly_in_base is None else round(monthly_in_base, 2),
            "conversion_quality": quality,
        })
    return {
        "payments": rows,
        "monthly_total_in_base": round(monthly_total, 2),
        "unconverted_count": unconverted,
        "missing_count": len(wanted or ()) - len(existing),
        "inactive_count": len(existing - {payment["id"] for payment in active}),
        "currency_conversion": currency.metadata(qualities),
    }


def transaction_log(db: Session, user_id: str, block: TransactionLogBlock, today: date) -> dict:
    """Entries in the range, newest first, with income and expense totals in base."""
    base = base_currency_for(db, user_id)
    snapshot = get_cached_rate_snapshot(base, db)
    rows = []
    for offset in RANGE_MONTHS[block.range or "this_month"]:
        year, month = _months_back(today, offset)
        rows.extend(month_transactions(
            db, user_id, year, month, kind=block.kind, category=block.category, limit=MONTH_ROW_LIMIT,
        ))

    totals = {TransactionKind.income.value: ZERO, TransactionKind.expense.value: ZERO}
    unconverted = 0
    entries = []
    for row in rows:
        value = amount_in_base(row, base, snapshot)
        if value is None:
            unconverted += 1
        else:
            totals[row.kind] += value
        if len(entries) < TRANSACTION_LOG_LIMIT:
            entries.append({**transaction_payload(row), "amount_in_base": None if value is None else _money(value)})
    return {
        "range": block.range or "this_month",
        "base_currency": base,
        "entries": entries,
        "entry_count": len(rows),
        "income": _money(totals[TransactionKind.income.value]),
        "expenses": _money(totals[TransactionKind.expense.value]),
        "unconverted_count": unconverted,
    }


def budget(db: Session, user_id: str, block: BudgetBlock, today: date) -> dict:
    """This month's budget rows, optionally for chosen categories only."""
    status = budget_status(db, user_id, today.year, today.month)
    if block.categories:
        chosen = {category.value for category in block.categories}
        status["budgets"] = [row for row in status["budgets"] if row["category"] in chosen]
    return status


def goal_progress(db: Session, user_id: str, block: GoalProgressBlock, today: date) -> dict:
    """Progress for the chosen goals, or every active goal when none are chosen."""
    wanted = {str(goal_id) for goal_id in block.goal_ids} if block.goal_ids else None
    goals = [
        {key: value for key, value in goal.items() if key != "contributions"}
        for goal in list_goals(include_archived=wanted is not None, user_id=user_id, db=db)
        if wanted is None or goal["id"] in wanted
    ]
    return {"goals": goals, "missing_count": _missing_count(db, user_id, Goal, block.goal_ids)}


def upcoming_payments(db: Session, user_id: str, block: UpcomingPaymentsBlock, today: date) -> dict:
    """Charges expected in the next few days, from the shared forecast."""
    forecast = get_upcoming_forecast(days=block.days, user_id=user_id, db=db)
    return {
        "days": block.days,
        "charges": [
            {
                key: charge[key]
                for key in (
                    "id", "name", "category", "amount", "currency", "due_at", "days_until_due",
                    "charge_kind", "charge_amount_in_base", "charge_amount_is_estimate",
                )
            }
            for charge in forecast["charges"]
        ],
        "total_in_base": forecast["forecast_total_in_base"],
        "unconverted_count": forecast["unconverted_occurrence_count"],
        "currency_conversion": forecast["currency_conversion"],
    }


def _category_total(spend: dict[str, Decimal], category: str | None) -> Decimal:
    return sum(spend.values(), ZERO) if category is None else spend.get(category, ZERO)


def _unconverted(counts: Counter[str], category: str | None) -> int:
    return sum(counts.values()) if category is None else counts.get(category, 0)


def spending_trend(db: Session, user_id: str, block: SpendingTrendBlock, today: date) -> dict:
    """Logged expenses and tracked payments charged, month by month, oldest first.

    Counted the way the Budgets screen counts: a logged expense linked to a
    payment charged that month is the same money, so only the payment counts.
    """
    category = block.category.value if block.category else None
    base = base_currency_for(db, user_id)
    snapshot = get_cached_rate_snapshot(base, db)
    months = []
    for offset in reversed(range(block.months)):
        year, month = _months_back(today, offset)
        payments = _CategorySpend()
        charged_ids = _add_tracked_payments(db, user_id, year, month, payments)
        logged = _CategorySpend()
        _add_logged_expenses(db, user_id, year, month, base, snapshot, charged_ids, logged)
        logged_unconverted = _unconverted(logged.unconverted, category)
        payments_unconverted = _unconverted(payments.unconverted, category)
        months.append({
            "month": f"{year:04d}-{month:02d}",
            "logged_expenses": _money(_category_total(logged.logged, category)),
            "tracked_payments": _money(_category_total(payments.payments, category)),
            "logged_unconverted_count": logged_unconverted,
            "payments_unconverted_count": payments_unconverted,
            "has_unconverted": bool(logged_unconverted or payments_unconverted),
        })
    return {"base_currency": base, "category": category, "months": months}


def checklist(db: Session, user_id: str, block: ChecklistBlock, today: date) -> dict:
    return {"items": [item.model_dump() for item in block.items]}


def notes(db: Session, user_id: str, block: NotesBlock, today: date) -> dict:
    return {"text": block.text}


def _split_in_cents(amount: Decimal, people: list[str]) -> dict[str, Decimal]:
    """Split equally; leftover cents go one each to the first people so shares add up exactly."""
    each = (amount / len(people)).quantize(CENTS, rounding=ROUND_DOWN)
    leftover_cents = int((amount - each * len(people)) / CENTS)
    return {person: each + (CENTS if index < leftover_cents else ZERO) for index, person in enumerate(people)}


def shared_costs(db: Session, user_id: str, block: SharedCostsBlock, today: date) -> dict:
    """What each person paid, their share and the net they owe (negative) or are owed."""
    paid = {person: ZERO for person in block.people}
    share = {person: ZERO for person in block.people}
    for item in block.items:
        paid[item.paid_by] += item.amount
        for person, portion in _split_in_cents(item.amount, item.split_between).items():
            share[person] += portion
    people = []
    for person in block.people:
        net = paid[person] - share[person]
        people.append({
            "name": person,
            "paid": _money(paid[person]),
            "share": _money(share[person]),
            "net": _money(net),
            "status": "is_owed" if net > 0 else "owes" if net < 0 else "settled",
        })
    return {
        "currency": block.currency or base_currency_for(db, user_id),
        "total": _money(sum((item.amount for item in block.items), ZERO)),
        "people": people,
    }


Resolver = Callable[[Session, str, Block, date], dict]

RESOLVERS: dict[str, Resolver] = {
    "payment_list": payment_list,
    "transaction_log": transaction_log,
    "budget": budget,
    "goal_progress": goal_progress,
    "upcoming_payments": upcoming_payments,
    "spending_trend": spending_trend,
    "checklist": checklist,
    "shared_costs": shared_costs,
    "notes": notes,
}


def _resolve_block(db: Session, user_id: str, raw: dict, today: date) -> dict:
    block_type = raw.get("type") if isinstance(raw, dict) else None
    title = raw.get("title") if isinstance(raw, dict) else None
    try:
        block = block_adapter.validate_python(raw)
    except ValidationError:
        logger.warning("Stored workspace block of type %r no longer validates", block_type)
        return {"type": block_type, "title": title, "error": BLOCK_FAILED}
    try:
        data = RESOLVERS[block.type](db, user_id, block, today)
    except Exception:  # noqa: BLE001 - one failing block must not take the whole page down
        # Roll back so a failed query does not stop later blocks from reading.
        logger.exception("Workspace block of type %s failed to load", block.type)
        db.rollback()
        return {"type": block.type, "title": block.title, "error": BLOCK_FAILED}
    return {"type": block.type, "title": block.title, "data": data}


def resolve_page_blocks(db: Session, user_id: str, raw_blocks: list[dict], today: date | None = None) -> list[dict]:
    """Each stored block in order, with its live data or its own error."""
    today = today or datetime.now(_user_zone(db, user_id)).date()
    return [_resolve_block(db, user_id, raw, today) for raw in raw_blocks]
