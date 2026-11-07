"""What was actually paid: past due dates lined up with email receipts.

- confirmed: a receipt for this payment arrived within a few days of the due
  date (or a receipt arrived that no due date explains, e.g. a moved date)
- expected: the schedule says it was due, but no receipt was seen
- extra: a recorded one-off such as a late fee

Receipts are matched to a payment by sender (the payment's source domain or a
saved "this is my X" link). When one sender bills several of the user's
payments (Apple Music and iCloud), the closest amount wins.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.agent.finance import CurrencyContext
from app.models import GmailReceipt, PaymentExtra, SenderLink, Subscription
from app.services.payment_links import merchant_key
from app.services.recurrence import forecast_end_for, occurrences_between, rewind_anchor, utc_naive

MATCH_WINDOW_DAYS = 4


def _receipt_owner(receipt: GmailReceipt, by_domain: dict, links: dict) -> Subscription | None:
    linked = links.get((receipt.intermediary, merchant_key(receipt.merchant or "")))
    if linked is not None:
        return linked
    candidates = by_domain.get(receipt.intermediary, [])
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    amount = float(receipt.amount)
    best = min(candidates, key=lambda sub: abs(float(sub.full_amount or sub.amount) - amount))
    regular = float(best.full_amount or best.amount)
    return best if regular and abs(regular - amount) <= regular * 0.1 else None


def paid_history(db: Session, user_id: str, *, months: int = 3, today: date | None = None) -> dict:
    today = today or datetime.utcnow().date()
    start = today - timedelta(days=31 * months)
    currency = CurrencyContext.for_user(db, user_id)

    subs = db.query(Subscription).filter(Subscription.user_id == user_id).all()
    by_id = {sub.id: sub for sub in subs}
    by_domain: dict[str, list[Subscription]] = {}
    for sub in subs:
        if sub.source_domain:
            by_domain.setdefault(sub.source_domain.lower(), []).append(sub)
    links = {
        (link.sender_domain, link.merchant_key): by_id.get(link.subscription_id)
        for link in db.query(SenderLink).filter(SenderLink.user_id == user_id)
    }

    receipts: dict = {}
    for receipt in db.query(GmailReceipt).filter(
        GmailReceipt.user_id == user_id,
        GmailReceipt.received_on >= start,
        GmailReceipt.received_on <= today,
    ):
        owner = _receipt_owner(receipt, by_domain, links)
        if owner is not None:
            receipts.setdefault(owner.id, []).append(receipt)

    rows: list[dict] = []

    def row(sub: Subscription, when: date, amount: float, native: str, status: str, kind: str) -> dict:
        in_base, _ = currency.convert(amount, native)
        return {
            "subscription_id": str(sub.id),
            "name": sub.name,
            "category": getattr(sub.category, "value", sub.category),
            "date": when.isoformat(),
            "amount": round(amount, 2),
            "currency": native,
            "amount_in_base": None if in_base is None else round(in_base, 2),
            "status": status,
            "kind": kind,
        }

    window_start = datetime.combine(start, datetime.min.time())
    window_end = datetime.combine(today, datetime.max.time())
    for sub in subs:
        unused = sorted(receipts.get(sub.id, []), key=lambda r: r.received_on)
        due_dates: list[date] = []
        if sub.next_due is not None:
            anchor = rewind_anchor(sub.next_due, sub, window_start)
            due_dates = [
                due.date() for due in occurrences_between(
                    anchor, sub, window_start, window_end,
                    recurrence_end_at=forecast_end_for(sub),
                )
            ]
        # Before the payment was added, a missing receipt proves nothing, so
        # only receipts (not "expected" rows) are shown for that period.
        tracked_since = utc_naive(sub.created_at).date() if sub.created_at else start
        for due in due_dates:
            match = next(
                (r for r in unused if abs((r.received_on - due).days) <= MATCH_WINDOW_DAYS), None,
            )
            if match is not None:
                unused.remove(match)
                rows.append(row(sub, match.received_on, float(match.amount), match.currency, "confirmed", "receipt"))
            elif sub.is_active and due >= tracked_since:
                rows.append(row(sub, due, float(sub.amount), sub.currency, "expected", "schedule"))
        for receipt in unused:
            rows.append(row(sub, receipt.received_on, float(receipt.amount), receipt.currency, "confirmed", "receipt"))

    for extra in db.query(PaymentExtra).filter(
        PaymentExtra.user_id == user_id,
        PaymentExtra.charged_at >= window_start,
    ):
        sub = by_id.get(extra.subscription_id)
        if sub is not None:
            rows.append(row(sub, utc_naive(extra.charged_at).date(), float(extra.amount),
                            extra.currency, "confirmed", "late_fee" if extra.reason == "late_fee" else "extra"))

    rows.sort(key=lambda r: (r["date"], r["name"].casefold()), reverse=True)
    return {"base_currency": currency.base, "since": start.isoformat(), "payments": rows}
