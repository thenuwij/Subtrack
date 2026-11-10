"""How each pay cycle went: pots planned against spent, savings, and other spends.

A pay cycle runs from one payday up to the next. Pots and savings use their
current amounts and count from the cycle they were added in; the response says
so, because past amounts aren't stored.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import SafeToSpendProfile, SetAside, Transaction, TransactionKind
from app.services.recurrence import rewind_anchor, utc_naive
from app.services.safe_to_spend import _local_date, _midnight, _next_payday, _previous_payday, _user_zone
from app.services.set_asides import _Rates, _to_base
from app.services.transactions import amount_in_base, base_currency_for

MAX_CYCLES = 26
NOTE = "Pots and savings use their current amounts, from the pay they were added in."


def _cycle_bounds(profile: SafeToSpendProfile, today: date, count: int) -> list[tuple[date, date]]:
    """The current cycle first, then ``count`` earlier ones, as (start, next payday)."""
    end = _next_payday(profile, today)
    start = _previous_payday(profile, end, today)
    bounds = [(start, end)]
    for _ in range(count):
        end = start
        start = rewind_anchor(
            _midnight(end), profile.pay_interval_unit, _midnight(end - timedelta(days=1)), profile.pay_interval_count,
        ).date()
        bounds.append((start, end))
    return bounds


def pay_cycles(db: Session, user_id: str, *, count: int = 6, now: datetime | None = None) -> dict:
    profile = db.get(SafeToSpendProfile, user_id)
    base = base_currency_for(db, user_id)
    if profile is None:
        return {"base_currency": base, "cycles": [], "note": NOTE}
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    today = _local_date(now, _user_zone(db, user_id))
    bounds = _cycle_bounds(profile, today, max(0, min(count, MAX_CYCLES)))
    rates = _Rates(db, base)

    set_asides = []
    for row in db.query(SetAside).filter(SetAside.user_id == user_id).order_by(SetAside.created_at, SetAside.id):
        amount = _to_base(row.amount_per_pay, row.currency, base, rates)
        added_on = utc_naive(row.created_at).date() if row.created_at else today
        set_asides.append((row, amount, added_on))

    earliest = bounds[-1][0]
    spends = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.kind == TransactionKind.expense.value,
            Transaction.recurring_payment_id.is_(None),
            Transaction.occurred_on >= earliest,
        )
        .order_by(Transaction.occurred_on.desc(), Transaction.created_at.desc())
        .all()
    )

    cycles = []
    for index, (start, end) in enumerate(bounds):
        in_cycle = [spend for spend in spends if start <= spend.occurred_on < end]
        values = {spend.id: amount_in_base(spend, base, rates.snapshot if spend.currency != base else None) for spend in in_cycle}
        pots, savings = [], []
        pot_ids = set()
        for row, amount, added_on in set_asides:
            if added_on >= end:
                continue  # added after this cycle
            if row.kind == "save":
                savings.append({"id": str(row.id), "name": row.name, "amount": float(amount) if amount is not None else None})
                continue
            pot_ids.add(row.id)
            spent = sum((values[s.id] or Decimal("0") for s in in_cycle if s.set_aside_id == row.id), Decimal("0"))
            planned = amount if amount is not None else None
            pots.append({
                "id": str(row.id),
                "name": row.name,
                "planned": float(planned) if planned is not None else None,
                "spent": float(spent),
                "left": float(max(planned - spent, Decimal("0"))) if planned is not None else None,
                "over": float(max(spent - planned, Decimal("0"))) if planned is not None else None,
            })
        other = [s for s in in_cycle if s.set_aside_id not in pot_ids]
        cycles.append({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "current": index == 0,
            "pots": pots,
            "savings": savings,
            "saved": float(sum((Decimal(str(s["amount"])) for s in savings if s["amount"] is not None), Decimal("0"))),
            "other_spent": float(sum((values[s.id] or Decimal("0") for s in other), Decimal("0"))),
            "spends": [
                {
                    "id": str(s.id),
                    "name": s.name,
                    "amount": float(values[s.id]) if values[s.id] is not None else None,
                    "occurred_on": s.occurred_on.isoformat(),
                    "pot": next((p["name"] for p in pots if p["id"] == str(s.set_aside_id)), None),
                }
                for s in in_cycle
            ],
        })
    return {"base_currency": base, "cycles": cycles, "note": NOTE}
