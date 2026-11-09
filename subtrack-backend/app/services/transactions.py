"""Currency conversion and monthly totals for day-to-day expenses and income.

The REST API and the assistant share these helpers so a logged entry is
converted and counted the same way whichever path created it.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Category, Transaction, TransactionKind, UserPreference
from app.routers.rates import conversion_for_storage, get_cached_rate_snapshot

CENTS = Decimal("0.01")
DEFAULT_BASE_CURRENCY = "AUD"
MONTH_ROW_LIMIT = 500


def base_currency_for(db: Session, user_id: str) -> str:
    preference = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    return preference.base_currency if preference and preference.base_currency else DEFAULT_BASE_CURRENCY


def _snapshot_time(snapshot: dict | None) -> datetime | None:
    if not snapshot or not snapshot.get("fetched_at"):
        return None
    return datetime.fromisoformat(snapshot["fetched_at"])


def apply_conversion(db: Session, row: Transaction, base: str) -> None:
    """Store the base-currency estimate from the shared snapshot, or none at all."""
    converted, _rate, quality = conversion_for_storage(float(row.amount), row.currency, base, db)
    if converted is None:
        row.base_amount = None
        row.base_currency = None
        row.rate_as_of = None
        return
    row.base_amount = Decimal(str(converted)).quantize(CENTS)
    row.base_currency = base
    row.rate_as_of = (
        None if quality == "exact_base_currency" else _snapshot_time(get_cached_rate_snapshot(base, db))
    )


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def month_transactions(
    db: Session,
    user_id: str,
    year: int,
    month: int,
    *,
    kind: TransactionKind | None = None,
    category: Category | None = None,
    limit: int = MONTH_ROW_LIMIT,
) -> list[Transaction]:
    """The user's entries dated in one month, newest first."""
    first, last = month_bounds(year, month)
    query = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.occurred_on.between(first, last),
    )
    if kind is not None:
        query = query.filter(Transaction.kind == kind.value)
    if category is not None:
        query = query.filter(Transaction.category == category)
    return (
        query.order_by(Transaction.occurred_on.desc(), Transaction.created_at.desc(), Transaction.id)
        .limit(limit)
        .all()
    )


def _amount_in_base(row: Transaction, base: str, snapshot: dict | None) -> Decimal | None:
    """Today's base-currency value of one entry, or None when no valid rate exists.

    A stored estimate is used only when it targets the current base currency;
    otherwise the native amount is re-expressed at the current shared snapshot.
    """
    if row.base_amount is not None and row.base_currency == base:
        return Decimal(row.base_amount)
    amount = Decimal(row.amount)
    if row.currency == base:
        return amount
    rate = (snapshot or {}).get("rates", {}).get(row.currency)
    if not isinstance(rate, (int, float)) or rate <= 0:
        return None
    return (amount / Decimal(str(rate))).quantize(CENTS)


def month_summary(db: Session, user_id: str, year: int, month: int) -> dict:
    """Income, expenses, net and per-category spending in the user's base currency.

    Entries without a valid conversion are counted in ``unconverted_count`` and
    left out of every total; they are never treated as 1:1.
    """
    base = base_currency_for(db, user_id)
    snapshot = get_cached_rate_snapshot(base, db)
    first, last = month_bounds(year, month)
    rows = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.occurred_on.between(first, last),
    ).all()

    income = Decimal("0")
    expenses = Decimal("0")
    by_category: dict[str, Decimal] = {}
    unconverted = 0
    for row in rows:
        value = _amount_in_base(row, base, snapshot)
        if value is None:
            unconverted += 1
            continue
        if row.kind == TransactionKind.income.value:
            income += value
            continue
        expenses += value
        category = row.category.value if isinstance(row.category, Category) else row.category
        by_category[category] = by_category.get(category, Decimal("0")) + value

    snapshot_time = _snapshot_time(snapshot)
    return {
        "month": f"{year:04d}-{month:02d}",
        "base_currency": base,
        "income": float(income),
        "expenses": float(expenses),
        "net": float(income - expenses),
        "expenses_by_category": {
            category: float(total)
            for category, total in sorted(by_category.items(), key=lambda item: (-item[1], item[0]))
        },
        "transaction_count": len(rows),
        "unconverted_count": unconverted,
        "rate_as_of": snapshot_time.isoformat() if snapshot_time else None,
        "rate_stale": bool(snapshot and snapshot.get("stale")),
    }
