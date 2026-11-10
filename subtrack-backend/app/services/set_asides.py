"""How set-asides and logged spends change what's free until payday.

- A savings set-aside comes off in full every pay cycle.
- A spending pot comes off as what's left in it this cycle, so a spend from
  the pot leaves free money unchanged until the pot runs out.
- Every logged spend comes off the money available, unless the balance
  already shows it (it was logged before the balance was entered).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import SetAside, Transaction, TransactionKind
from app.routers.rates import get_cached_rate_snapshot
from app.services.transactions import CENTS, amount_in_base


class _Rates:
    """Loads the shared rate snapshot only if a foreign amount needs it."""

    def __init__(self, db: Session, base: str):
        self.db, self.base, self._snapshot, self._loaded = db, base, None, False

    @property
    def snapshot(self) -> dict | None:
        if not self._loaded:
            self._snapshot, self._loaded = get_cached_rate_snapshot(self.base, self.db), True
        return self._snapshot


def _to_base(amount: Decimal, currency: str, base: str, rates: _Rates) -> Decimal | None:
    if currency == base:
        return Decimal(amount).quantize(CENTS)
    rate = (rates.snapshot or {}).get("rates", {}).get(currency)
    if not isinstance(rate, (int, float)) or rate <= 0:
        return None
    return (Decimal(amount) / Decimal(str(rate))).quantize(CENTS)


def set_aside_position(
    db: Session,
    user_id: str,
    *,
    base: str,
    cycle_start: date,
    cycle_end: date,
    balance_as_of: datetime | None,
) -> dict | None:
    """Reserved and spent amounts for this pay cycle, or None if a currency can't be converted.

    ``balance_as_of`` is None for an estimate from pay, where every spend this
    cycle counts; with a balance, only spends logged after it count.
    """
    rates = _Rates(db, base)
    rows = (
        db.query(SetAside)
        .filter(SetAside.user_id == user_id)
        .order_by(SetAside.created_at, SetAside.id)
        .all()
    )
    spends = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.kind == TransactionKind.expense.value,
            Transaction.recurring_payment_id.is_(None),
            Transaction.occurred_on >= cycle_start,
            Transaction.occurred_on < cycle_end,
        )
        .order_by(Transaction.occurred_on, Transaction.created_at)
        .all()
    )

    items = []
    for row in rows:
        amount = _to_base(row.amount_per_pay, row.currency, base, rates)
        if amount is None:
            return None
        items.append({
            "id": str(row.id), "kind": row.kind, "name": row.name, "amount": amount,
            "target_amount": float(row.target_amount) if row.target_amount is not None else None,
            "spent": Decimal("0"),
        })
    pots = {item["id"]: item for item in items if item["kind"] == "pot"}

    spent_counted = Decimal("0")
    spend_rows = []
    for spend in spends:
        foreign = spend.currency != base and not (spend.base_amount is not None and spend.base_currency == base)
        value = amount_in_base(spend, base, rates.snapshot if foreign else None)
        if value is None:
            return None
        counted = balance_as_of is None or spend.created_at > balance_as_of
        pot = pots.get(str(spend.set_aside_id)) if spend.set_aside_id else None
        if pot:
            pot["spent"] += value
        if counted:
            spent_counted += value
        spend_rows.append({
            "id": str(spend.id), "name": spend.name, "amount": float(value),
            "occurred_on": spend.occurred_on.isoformat(),
            "set_aside_id": str(spend.set_aside_id) if pot else None,
        })

    reserved = Decimal("0")
    for item in items:
        if item["kind"] == "save":
            reserved += item["amount"]
            continue
        left = max(item["amount"] - item["spent"], Decimal("0"))
        reserved += left
        item["left"] = float(left)

    return {
        "reserved": reserved,
        "spent": spent_counted,
        "set_asides": [
            {
                "id": item["id"], "kind": item["kind"], "name": item["name"],
                "amount": float(item["amount"]), "target_amount": item["target_amount"],
                **({"spent": float(item["spent"]), "left": item["left"]} if item["kind"] == "pot" else {}),
            }
            for item in items
        ],
        "spends": spend_rows,
    }
