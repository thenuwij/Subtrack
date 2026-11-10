"""Payments that already fell due and are still unpaid.

Safe to spend counts bills from the balance date (or the start of the pay
cycle) up to payday. A bill that fell due before then and still isn't paid,
like rent paid late, is still money owed, so it is counted too:

- a scheduled payment the user marked "Not paid yet" in Paid history;
- a pay-it-myself payment still on the To pay list, up to 60 days back and
  never before the payment was added.

Marking it paid (or undoing the answer) stops it being counted.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.agent.finance import CurrencyContext, upcoming_charges
from app.models import PaymentDecision, Subscription, Transaction
from app.services.recurrence import utc_naive

LOOKBACK_DAYS = 60


def _target_parts(target: str) -> tuple[str, date] | None:
    kind, _, rest = target.partition(":")
    sub_id, _, due = rest.rpartition(":")
    if kind != "payment" or not sub_id:
        return None
    try:
        return sub_id, date.fromisoformat(due)
    except ValueError:
        return None


def overdue_unpaid(
    db: Session, user_id: str, *, before: date, today: date, zone: ZoneInfo, currency: CurrencyContext,
) -> list[dict] | None:
    """Owed payments due before ``before``; None when an amount can't be converted."""
    subs = {str(sub.id): sub for sub in db.query(Subscription).filter(Subscription.user_id == user_id)}
    decisions = {
        row.target: row.decision
        for row in db.query(PaymentDecision).filter(PaymentDecision.user_id == user_id)
    }
    owed: dict[tuple[str, date], Subscription] = {}

    for target, decision in decisions.items():
        parts = _target_parts(target) if decision == "unpaid" else None
        if parts and parts[1] < before and parts[0] in subs and subs[parts[0]].is_active:
            owed[parts] = subs[parts[0]]

    manual_ids = {sub_id for sub_id, sub in subs.items() if sub.payment_method == "manual" and sub.is_active}
    start = max(today - timedelta(days=LOOKBACK_DAYS), date.min)
    if manual_ids and start < before:
        paid = {
            (str(payment_id), due_on)
            for payment_id, due_on in db.query(Transaction.recurring_payment_id, Transaction.paid_due_on).filter(
                Transaction.user_id == user_id,
                Transaction.paid_due_on.isnot(None),
                Transaction.paid_due_on >= start,
            )
        }
        charges = upcoming_charges(
            db,
            user_id,
            start_at=datetime.combine(start, time.min, tzinfo=zone),
            end_at=datetime.combine(before, time.min, tzinfo=zone) - timedelta(microseconds=1),
            include_past=True,
        )["charges"]
        for charge in charges:
            if charge["id"] not in manual_ids:
                continue
            due_on = datetime.fromisoformat(charge["due_at"]).replace(tzinfo=timezone.utc).astimezone(zone).date()
            answer = decisions.get(f"payment:{charge['id']}:{due_on.isoformat()}")
            sub = subs[charge["id"]]
            # Before the payment was added, a missing payment proves nothing.
            added_on = utc_naive(sub.created_at).date() if sub.created_at else today
            if due_on >= added_on and (charge["id"], due_on) not in paid and answer not in ("paid", "skipped"):
                owed[(charge["id"], due_on)] = subs[charge["id"]]

    rows = []
    for (sub_id, due_on), sub in sorted(owed.items(), key=lambda item: (item[0][1], item[1].name)):
        amount, _ = currency.convert(float(sub.amount), sub.currency, stored_amount=sub.converted_amount)
        if amount is None:
            return None
        rows.append({
            "id": sub_id,
            "name": sub.name,
            "category": sub.category.value,
            "due_at": datetime.combine(due_on, time(12)).isoformat(),
            "amount": round(amount, 2),
            "is_estimate": False,
            "overdue": True,
        })
    return rows
