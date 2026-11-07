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

import re
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.agent.finance import CurrencyContext
from app.models import GmailReceipt, PaymentExtra, SenderLink, Subscription
from app.services.payment_links import merchant_key, name_words
from app.services.recurrence import forecast_end_for, occurrences_between, rewind_anchor, utc_naive

MATCH_WINDOW_DAYS = 4


# Parts of a sender address that say nothing about who it is.
SENDER_NOISE = {
    "com", "au", "net", "org", "co", "io", "mail", "email", "emails", "noreply", "no", "reply",
    "mybill", "billing", "bill", "info", "hello", "notifications", "news", "comms", "retail",
    "account", "accounts", "members", "receipts", "invoice", "statements",
}


# Products sold under a parent brand's sender.
BRAND_SENDERS = {
    "icloud": "apple", "itunes": "apple", "youtube": "google", "claude": "anthropic",
    "chatgpt": "openai", "prime": "amazon", "xbox": "microsoft",
}
# Senders that bill for a category rather than naming the product.
CATEGORY_SENDERS = {
    "housing": ("property", "realestate", "realty", "rent", "strata", "lettings"),
}


# Bills that charge a late fee when paid late. Anything paid above the
# regular price is a fee, and one late payment can cover several periods.
FEE_CATEGORIES = {"phone_internet", "utilities", "fitness", "memberships", "housing", "insurance"}
# How long after a due date a late payment can still be the one that paid it.
LATE_WINDOW_DAYS = 70
MIN_FEE = 0.5


# Pay-later and payment platforms send a receipt for every purchase, so their
# receipts only ever match a payment at its exact price.
PAY_LATER_SENDERS = ("afterpay", "zip.co", "klarna", "paypal", "humm", "openpay", "laybuy")


def _pay_later(receipt: GmailReceipt) -> bool:
    return any(name in receipt.intermediary.lower() for name in PAY_LATER_SENDERS)


def _charges_late_fees(sub: Subscription) -> bool:
    return not _is_variable(sub) and getattr(sub.category, "value", sub.category) in FEE_CATEGORIES


def _split_payment(sub: Subscription, amount: float) -> tuple[int, float]:
    """How many periods a receipt paid for, and the late fee on top."""
    regular = _regular(sub)
    if not regular or not _charges_late_fees(sub) or amount < regular + MIN_FEE:
        return 1, 0.0
    periods = max(1, int(amount / regular + 0.05))
    fee = round(amount - periods * regular, 2)
    return periods, fee if fee >= MIN_FEE else 0.0


def _is_variable(sub: Subscription) -> bool:
    return getattr(sub.amount_type, "value", sub.amount_type) == "variable"


def _amount_fits(sub: Subscription, amount: float, receipt: GmailReceipt | None = None) -> bool:
    """Close to the regular (whole-bill) price, or to an intro price."""
    tolerance = 0.6 if _is_variable(sub) else 0.1
    if _close(sub, amount, tolerance):
        return True
    # A late payment: one or more periods plus fees.
    regular = _regular(sub)
    if receipt is not None and _pay_later(receipt):
        return False
    if _charges_late_fees(sub) and regular and regular * 0.9 <= amount <= regular * 3.2:
        return True
    intro = float(sub.intro_amount) if sub.intro_amount is not None else None
    return intro is not None and abs(intro - amount) <= max(intro * tolerance, 0.05)


def _regular(sub: Subscription) -> float:
    """What the biller charges: the whole bill for a shared payment."""
    return float(sub.full_amount or sub.amount)


def _close(sub: Subscription, amount: float, tolerance: float) -> bool:
    regular = _regular(sub)
    return bool(regular) and abs(regular - amount) <= regular * tolerance


def _named_in(sub: Subscription, receipt: GmailReceipt) -> bool:
    """The payment's name shows up in the sender's address or business name.

    "Vodafone" ↔ mybill.vodafone.com.au, "Origin Energy" ↔ originenergy.com.au.
    """
    sender = [part for part in re.split(r"[.\-]", receipt.intermediary.lower()) if part not in SENDER_NOISE]
    haystack = " ".join(sender + [(receipt.merchant or "").lower()])
    words = [word for word in name_words(sub.name) if len(word) >= 4]
    if words and (words[0] in haystack or BRAND_SENDERS.get(words[0], "\0") in haystack):
        return True
    category = getattr(sub.category, "value", sub.category)
    return any(hint in haystack for hint in CATEGORY_SENDERS.get(category, ()))


def _receipt_owner(
    receipt: GmailReceipt, by_domain: dict, links: dict, active: list[Subscription],
) -> Subscription | None:
    linked = links.get((receipt.intermediary, merchant_key(receipt.merchant or "")))
    if linked is not None:
        return linked
    # Billing platforms (Debitsuccess) put their own name on receipts, not the
    # gym's. With only one saved link for that sender, it's that payment.
    domain_links = {sub.id: sub for (domain, _key), sub in links.items() if domain == receipt.intermediary and sub}
    if len(domain_links) == 1:
        return next(iter(domain_links.values()))
    amount = float(receipt.amount)
    candidates = [sub for sub in by_domain.get(receipt.intermediary, []) if _amount_fits(sub, amount, receipt)]
    if candidates:
        return min(candidates, key=lambda sub: abs(_regular(sub) - amount))
    # Payments added by hand have no sender on record, so fall back to the
    # name. A name match alone is weaker, so the amount must be close too
    # (variable bills such as electricity are allowed to move more).
    named = [sub for sub in active if _named_in(sub, receipt) and _amount_fits(sub, amount, receipt)]
    if not named:
        return None
    return min(named, key=lambda sub: abs(_regular(sub) - amount))


def _your_part(sub: Subscription, receipt: GmailReceipt) -> float:
    """A receipt for a shared bill shows the whole bill; show the user's share."""
    amount = float(receipt.amount)
    if sub.full_amount and _close(sub, amount, 0.1):
        return float(sub.amount)
    return amount


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
    active = [sub for sub in subs if sub.is_active]
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
        owner = _receipt_owner(receipt, by_domain, links, active)
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
    recorded_fees = [
        extra for extra in db.query(PaymentExtra).filter(
            PaymentExtra.user_id == user_id,
            PaymentExtra.charged_at >= window_start,
        )
    ]

    for sub in subs:
        # Each receipt can pay one or more periods; track what's left on it.
        left = []
        for receipt in sorted(receipts.get(sub.id, []), key=lambda r: r.received_on):
            periods, fee = _split_payment(sub, float(receipt.amount))
            left.append([receipt, periods, fee])
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
        late_ok = LATE_WINDOW_DAYS if _charges_late_fees(sub) else MATCH_WINDOW_DAYS
        for due in due_dates:
            match = next(
                (entry for entry in left
                 if entry[1] > 0 and -MATCH_WINDOW_DAYS <= (entry[0].received_on - due).days <= late_ok),
                None,
            )
            if match is not None:
                receipt = match[0]
                match[1] -= 1
                # "Late" means it cost a fee, not just a few days' drift.
                late = bool(match[2])
                rows.append(row(sub, receipt.received_on, float(sub.amount) if late or match[2] else _your_part(sub, receipt),
                                receipt.currency, "confirmed", "late" if late else "receipt"))
            elif sub.is_active and due >= tracked_since:
                rows.append(row(sub, due, float(sub.amount), sub.currency, "expected", "schedule"))
        for receipt, periods, fee in left:
            used = _split_payment(sub, float(receipt.amount))[0] - periods
            if used == 0:
                # No due date explains it (e.g. the schedule is off); still paid.
                rows.append(row(sub, receipt.received_on, _your_part(sub, receipt) if not fee else float(sub.amount),
                                receipt.currency, "confirmed", "receipt"))
            already_recorded = any(
                extra.subscription_id == sub.id
                and abs((utc_naive(extra.charged_at).date() - receipt.received_on).days) <= MATCH_WINDOW_DAYS
                for extra in recorded_fees
            )
            if fee and not already_recorded:
                rows.append(row(sub, receipt.received_on, fee, receipt.currency, "confirmed", "late_fee"))

    for extra in recorded_fees:
        sub = by_id.get(extra.subscription_id)
        if sub is not None:
            rows.append(row(sub, utc_naive(extra.charged_at).date(), float(extra.amount),
                            extra.currency, "confirmed", "late_fee" if extra.reason == "late_fee" else "extra"))

    rows.sort(key=lambda r: (r["date"], r["name"].casefold()), reverse=True)
    late_fees = round(sum(r["amount_in_base"] or 0 for r in rows if r["kind"] == "late_fee"), 2)
    return {
        "base_currency": currency.base,
        "since": start.isoformat(),
        "late_fees_total": late_fees,
        "payments": rows,
    }
