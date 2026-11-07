"""What was actually paid, built from bills (what's owed) and receipts (what was paid).

Bills are the source of truth for payments that send invoices (Vodafone,
Origin, water). Receipts only mark those bills as paid, part paid or still
owing; nothing is worked out backwards from how much someone chose to pay.

Payments without invoices (Netflix, Apple, the gym) are lined up against their
schedule instead:

- confirmed: a receipt arrived within a few days of the due date
- expected: the schedule says it was due, but no receipt was seen
- above plan: a charge higher than the plan price that the user hasn't sorted
  yet (late fee, or not a fee). It is never counted as a late fee on its own.

Late fees come only from a bill that states one, or from the user saying so.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.agent.finance import CurrencyContext
from app.models import Bill, GmailReceipt, PaymentDecision, PaymentExtra, SenderLink, Subscription
from app.services.payment_links import merchant_key, name_words
from app.services.recurrence import forecast_end_for, occurrences_between, rewind_anchor, utc_naive

MATCH_WINDOW_DAYS = 4
MIN_ABOVE_PLAN = 0.5

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
# Pay-later and payment platforms send a receipt for every purchase, so their
# receipts only ever match a payment at its exact price.
PAY_LATER_SENDERS = ("afterpay", "zip.co", "klarna", "paypal", "humm", "openpay", "laybuy")


def _value(field) -> str:
    return getattr(field, "value", field)


def _regular(sub: Subscription) -> float:
    """What the biller charges: the whole bill for a shared payment."""
    return float(sub.full_amount or sub.amount)


def _close(sub: Subscription, amount: float, tolerance: float) -> bool:
    regular = _regular(sub)
    return bool(regular) and abs(regular - amount) <= regular * tolerance


def _amount_fits(sub: Subscription, amount: float) -> bool:
    """Close to the regular (whole-bill) price, or to an intro price."""
    tolerance = 0.6 if _value(sub.amount_type) == "variable" else 0.1
    if _close(sub, amount, tolerance):
        return True
    intro = float(sub.intro_amount) if sub.intro_amount is not None else None
    return intro is not None and abs(intro - amount) <= max(intro * tolerance, 0.05)


def _named_in(sub: Subscription, sender: str, merchant: str | None) -> bool:
    """The payment's name shows up in the sender's address or business name.

    "Vodafone" ↔ mybill.vodafone.com.au, "Origin Energy" ↔ originenergy.com.au.
    """
    parts = [part for part in re.split(r"[.\-]", sender.lower()) if part not in SENDER_NOISE]
    haystack = " ".join(parts + [(merchant or "").lower()])
    words = [word for word in name_words(sub.name) if len(word) >= 4]
    if words and (words[0] in haystack or BRAND_SENDERS.get(words[0], "\0") in haystack):
        return True
    return any(hint in haystack for hint in CATEGORY_SENDERS.get(_value(sub.category), ()))


class _Matcher:
    """Finds which tracked payment a bill or receipt belongs to."""

    def __init__(self, subs: list[Subscription], links: dict):
        self.links = links
        self.active = [sub for sub in subs if sub.is_active]
        self.by_domain: dict[str, list[Subscription]] = {}
        for sub in subs:
            if sub.source_domain:
                self.by_domain.setdefault(sub.source_domain.lower(), []).append(sub)
        # Senders that send this user bills, and whose payment they're for.
        self.bill_senders: dict[str, Subscription] = {}

    def _linked(self, sender: str, merchant: str | None) -> Subscription | None:
        linked = self.links.get((sender, merchant_key(merchant or "")))
        if linked is not None:
            return linked
        # Billing platforms (Debitsuccess) put their own name on receipts, not
        # the gym's. With only one saved link for that sender, it's that payment.
        for_sender = {sub.id: sub for (domain, _key), sub in self.links.items() if domain == sender and sub}
        return next(iter(for_sender.values())) if len(for_sender) == 1 else None

    def bill_owner(self, bill: Bill) -> Subscription | None:
        """Bill amounts vary (balances, usage), so they match on sender and name only."""
        owner = self._linked(bill.intermediary, bill.merchant)
        if owner is None:
            by_domain = self.by_domain.get(bill.intermediary, [])
            named = by_domain or [sub for sub in self.active if _named_in(sub, bill.intermediary, bill.merchant)]
            owner = named[0] if len(named) == 1 else None
        # A bill nowhere near the payment's price is a different bill from the
        # same sender (a water invoice from the rent agent).
        if owner is not None and bill.amount is not None and _value(owner.amount_type) != "variable":
            regular = _regular(owner)
            if regular and not regular * 0.5 <= float(bill.amount) <= regular * 3.5:
                owner = None
        if owner is not None:
            self.bill_senders[bill.intermediary] = owner
        return owner

    def receipt_owner(self, receipt: GmailReceipt) -> Subscription | None:
        sender, amount = receipt.intermediary, float(receipt.amount)
        owner = self._linked(sender, receipt.merchant)
        if owner is not None:
            return owner
        # A sender that bills this payment: its receipts pay those bills,
        # whatever the amount (part payments, catching up, credit).
        if sender in self.bill_senders:
            return self.bill_senders[sender]
        exact_only = any(name in sender.lower() for name in PAY_LATER_SENDERS)
        candidates = [sub for sub in self.by_domain.get(sender, []) if _amount_fits(sub, amount)]
        if not candidates:
            # Payments added by hand have no sender on record, so fall back to
            # the name, with the amount close too.
            candidates = [
                sub for sub in self.active
                if _named_in(sub, sender, receipt.merchant) and _amount_fits(sub, amount)
            ]
        if exact_only:
            candidates = [sub for sub in candidates if _close(sub, amount, 0.01)]
        return min(candidates, key=lambda sub: abs(_regular(sub) - amount)) if candidates else None


def _your_part(sub: Subscription, amount: float) -> float:
    """A receipt for a shared bill shows the whole bill; show the user's share."""
    if sub.full_amount and _close(sub, amount, 0.1):
        return float(sub.amount)
    return amount


def _bill_statuses(bills: list[Bill], receipts: list[GmailReceipt], today: date) -> list[dict]:
    """Apply receipts to bills. A receipt pays the latest bill issued before it.

    Bills like Vodafone's carry an unpaid balance into the next bill, so
    everything paid between two bills counts towards the earlier one.
    """
    ordered = sorted(bills, key=lambda bill: bill.issued_on)
    out = []
    for index, bill in enumerate(ordered):
        until = ordered[index + 1].issued_on if index + 1 < len(ordered) else date.max
        paid_on = [r for r in receipts if bill.issued_on <= r.received_on < until]
        paid = round(sum(float(r.amount) for r in paid_on), 2)
        amount = float(bill.amount) if bill.amount is not None else None
        if amount is None:
            status = "paid" if paid else "unknown"
        elif paid >= amount - 0.01:
            status = "credit" if paid > amount + 0.01 else "paid"
        elif bill.due_on and bill.due_on < today:
            status = "overdue"
        elif paid:
            status = "part_paid"
        else:
            status = "due"
        out.append({
            "bill": bill,
            "paid": paid,
            "paid_on": max((r.received_on for r in paid_on), default=None),
            "owing": round(max((amount or 0) - paid, 0), 2) if amount is not None else None,
            "status": status,
        })
    # Unpaid balances carry into the next bill, so a later bill paid in full
    # settles the ones before it.
    settled = False
    for state in reversed(out):
        if state["status"] in ("paid", "credit"):
            settled = True
        elif settled and state["status"] in ("overdue", "part_paid", "due"):
            state["status"] = "carried"
            state["owing"] = 0.0
    return out


def paid_history(db: Session, user_id: str, *, months: int = 3, today: date | None = None) -> dict:
    today = today or datetime.utcnow().date()
    start = today - timedelta(days=31 * months)
    currency = CurrencyContext.for_user(db, user_id)

    subs = db.query(Subscription).filter(Subscription.user_id == user_id).all()
    decisions = {d.target: d.decision for d in db.query(PaymentDecision).filter(PaymentDecision.user_id == user_id)}
    by_id = {sub.id: sub for sub in subs}
    links = {
        (link.sender_domain, link.merchant_key): by_id.get(link.subscription_id)
        for link in db.query(SenderLink).filter(SenderLink.user_id == user_id)
    }
    matcher = _Matcher(subs, links)

    bills_by_sub: dict = {}
    loose_bills: dict[str, list[Bill]] = {}
    for bill in db.query(Bill).filter(Bill.user_id == user_id, Bill.issued_on >= start, Bill.issued_on <= today):
        owner = matcher.bill_owner(bill)
        if owner is not None:
            bills_by_sub.setdefault(owner.id, []).append(bill)
        else:
            loose_bills.setdefault(bill.intermediary, []).append(bill)

    receipts: dict = {}
    loose_receipts: dict[str, list[GmailReceipt]] = {}
    for receipt in db.query(GmailReceipt).filter(
        GmailReceipt.user_id == user_id,
        GmailReceipt.received_on >= start,
        GmailReceipt.received_on <= today,
    ):
        owner = matcher.receipt_owner(receipt)
        if owner is not None:
            receipts.setdefault(owner.id, []).append(receipt)
        else:
            loose_receipts.setdefault(receipt.intermediary, []).append(receipt)

    window_start = datetime.combine(start, datetime.min.time())
    window_end = datetime.combine(today, datetime.max.time())
    extras = db.query(PaymentExtra).filter(
        PaymentExtra.user_id == user_id, PaymentExtra.charged_at >= window_start,
    ).all()

    def in_base(amount: float, native: str) -> float | None:
        value, _ = currency.convert(amount, native)
        return None if value is None else round(value, 2)

    def row(sub: Subscription, when: date, amount: float, native: str, status: str, kind: str, **more) -> dict:
        return {
            "subscription_id": str(sub.id),
            "name": sub.name,
            "category": _value(sub.category),
            "date": when.isoformat(),
            "amount": round(amount, 2),
            "currency": native,
            "amount_in_base": in_base(amount, native),
            "status": status,
            "kind": kind,
            **more,
        }

    def sorted_near(sub: Subscription, when: date) -> bool:
        """The user already said whether a charge near this date was a fee."""
        return any(
            extra.subscription_id == sub.id
            and abs((utc_naive(extra.charged_at).date() - when).days) <= MATCH_WINDOW_DAYS
            for extra in extras
        )

    rows: list[dict] = []
    bill_rows: list[dict] = []
    late_fees = 0.0

    def add_bills(bills: list[Bill], paid_with: list[GmailReceipt], sub: Subscription | None) -> None:
        nonlocal late_fees
        for state in _bill_statuses(bills, paid_with, today):
            bill = state["bill"]
            fee = float(bill.late_fee) if bill.late_fee is not None else None
            if fee:
                late_fees += in_base(fee, bill.currency) or 0
            target = f"bill:{bill.id}"
            manual = decisions.get(target)
            if manual == "paid" and state["status"] not in ("paid", "credit", "carried"):
                state.update(status="paid", paid=amount if (amount := bill.amount) is not None else 0, owing=0)
            bill_rows.append({
                "target": target, "manual": manual,
                "id": str(bill.id),
                "subscription_id": str(sub.id) if sub else None,
                # "Ratika Arora - Whome Group" -> "Whome Group": the business, not the person.
                "name": sub.name if sub else ((bill.merchant or bill.intermediary).split(" - ")[-1]),
                "category": _value(sub.category) if sub else "other",
                "issued_on": bill.issued_on.isoformat(),
                "due_on": bill.due_on.isoformat() if bill.due_on else None,
                "amount": float(bill.amount) if bill.amount is not None else None,
                "currency": bill.currency,
                "paid": state["paid"],
                "paid_on": state["paid_on"].isoformat() if state["paid_on"] else None,
                "owing": state["owing"],
                "status": state["status"],
                "late_fee": fee,
                "tracked": sub is not None,
            })

    # Bills for payments not tracked yet (still in Inbox) still show. Their
    # receipts can come from a sibling address (origin.com.au bills,
    # originenergy.com.au receipts), so match on the sender's core name.
    def core(sender: str) -> str:
        parts = [part for part in re.split(r"[.\-]", sender.lower()) if part not in SENDER_NOISE]
        return parts[0] if parts else sender

    for sender, bills in loose_bills.items():
        name = core(sender)
        paid_with = [r for other, found in loose_receipts.items() if name in other.lower() for r in found]
        add_bills(bills, paid_with, None)

    for sub in subs:
        sub_receipts = sorted(receipts.get(sub.id, []), key=lambda r: r.received_on)

        if sub.id in bills_by_sub:
            # Invoiced payments: bills say what was owed, receipts mark them paid.
            add_bills(bills_by_sub[sub.id], sub_receipts, sub)
            for receipt in sub_receipts:
                rows.append(row(sub, receipt.received_on, float(receipt.amount), receipt.currency, "confirmed", "receipt"))
            continue

        # Payments without invoices: line receipts up with the schedule.
        unused = list(sub_receipts)
        due_dates: list[date] = []
        if sub.next_due is not None:
            anchor = rewind_anchor(sub.next_due, sub, window_start)
            due_dates = [
                due.date() for due in occurrences_between(
                    anchor, sub, window_start, window_end, recurrence_end_at=forecast_end_for(sub),
                )
            ]
        # Before the payment was added, a missing receipt proves nothing.
        tracked_since = utc_naive(sub.created_at).date() if sub.created_at else start
        matched: list[GmailReceipt] = []
        for due in due_dates:
            match = next((r for r in unused if abs((r.received_on - due).days) <= MATCH_WINDOW_DAYS), None)
            if match is not None:
                unused.remove(match)
                matched.append(match)
            elif sub.is_active and due >= tracked_since:
                target = f"payment:{sub.id}:{due.isoformat()}"
                manual = decisions.get(target)
                rows.append(row(sub, due, float(sub.amount), sub.currency,
                    "confirmed" if manual == "paid" else "skipped" if manual == "skipped" else "expected",
                    "schedule", target=target, manual=manual))
        for receipt in matched + unused:
            amount = float(receipt.amount)
            above = round(amount - _regular(sub), 2)
            fixed = _value(sub.amount_type) != "variable"
            if fixed and above >= MIN_ABOVE_PLAN and not sorted_near(sub, receipt.received_on):
                rows.append(row(sub, receipt.received_on, float(sub.amount), receipt.currency, "confirmed", "receipt"))
                rows.append(row(sub, receipt.received_on, above, receipt.currency, "unsorted", "above_plan"))
            else:
                rows.append(row(sub, receipt.received_on, _your_part(sub, amount), receipt.currency, "confirmed", "receipt"))

    for extra in extras:
        sub = by_id.get(extra.subscription_id)
        if sub is None or extra.reason == "not_fee":
            continue
        kind = "late_fee" if extra.reason == "late_fee" else "extra"
        rows.append(row(sub, utc_naive(extra.charged_at).date(), float(extra.amount), extra.currency, "confirmed", kind))
        if kind == "late_fee":
            late_fees += in_base(float(extra.amount), extra.currency) or 0

    rows.sort(key=lambda r: (r["date"], r["name"].casefold()), reverse=True)
    bill_rows.sort(key=lambda b: b["issued_on"], reverse=True)
    above_plan = sum(r["amount_in_base"] or 0 for r in rows if r["kind"] == "above_plan")
    return {
        "base_currency": currency.base,
        "since": start.isoformat(),
        "late_fees_total": round(late_fees, 2),
        "above_plan_total": round(above_plan, 2),
        "bills": bill_rows,
        "payments": rows,
    }
