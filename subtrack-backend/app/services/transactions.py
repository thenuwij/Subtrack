"""Currency conversion for logged spends and payments marked paid.

Every write path uses these helpers so an entry is converted and counted the
same way whichever path created it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Category, Transaction, UserPreference
from app.routers.rates import conversion_for_storage, get_cached_rate_snapshot

CENTS = Decimal("0.01")
DEFAULT_BASE_CURRENCY = "AUD"


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


def amount_in_base(row: Transaction, base: str, snapshot: dict | None) -> Decimal | None:
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


def transaction_payload(row: Transaction) -> dict:
    return {
        "id": str(row.id),
        "kind": row.kind,
        "name": row.name,
        "amount": float(row.amount),
        "currency": row.currency,
        "base_amount": float(row.base_amount) if row.base_amount is not None else None,
        "base_currency": row.base_currency,
        "rate_as_of": row.rate_as_of.isoformat() if row.rate_as_of else None,
        "category": row.category.value if isinstance(row.category, Category) else row.category,
        "occurred_on": row.occurred_on.isoformat(),
        "note": row.note,
        "source": row.source,
        "recurring_payment_id": str(row.recurring_payment_id) if row.recurring_payment_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
