"""Read a bill (invoice) email: how much is owed, when it's due, any late fee.

Bills are the source of truth for what's owed; receipts only mark bills as
paid. Anything an email doesn't state is left empty so the user is asked,
never guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

MONEY = r"\$\s?(\d[\d,]*\.\d{2})"

# A bill or invoice asks for money; a receipt confirms it was paid.
BILL_SUBJECT = re.compile(r"(?i)(\bbill\b|invoice due|new invoice|statement|amount due)")
RECEIPT_WORDS = re.compile(r"(?i)(receipt|thanks for your payment|payment received|tax invoice)")

AMOUNT_DUE = [
    re.compile(r"(?i)total balance due\W{0,20}" + MONEY),
    re.compile(r"(?i)amount owing is\W{0,5}" + MONEY),
    re.compile(r"(?i)amount (?:due|owing)\W{0,20}" + MONEY),
    re.compile(r"(?i)new charges\W{0,20}" + MONEY),
    re.compile(r"(?i)total (?:amount )?due\W{0,20}" + MONEY),
]
DUE_DATE = [
    # "due for payment on 6/11/2026", "due on 06/11/2026"
    re.compile(r"(?i)due (?:for payment )?(?:on|by)?\s*(\d{1,2}/\d{1,2}/\d{4})"),
    # "Due 03 Nov 2026", "due by 3 November 2026"
    re.compile(r"(?i)due(?: date)?(?: on| by)?:?\s*(\d{1,2} [A-Za-z]{3,9} \d{4})"),
]
LATE_FEE = re.compile(r"(?i)(?:late (?:payment )?fee|overdue fee|dishonou?r fee)\W{0,20}" + MONEY)


@dataclass
class BillDetails:
    amount_due: float | None
    due_on: date | None
    late_fee: float | None


def _money(text: str) -> float:
    return float(text.replace(",", ""))


def _date(text: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def is_bill(subject: str) -> bool:
    return bool(BILL_SUBJECT.search(subject or "")) and not RECEIPT_WORDS.search(subject or "")


def read_bill(subject: str, body: str) -> BillDetails | None:
    """Details from a bill email, or None if it isn't one."""
    if not is_bill(subject):
        return None
    text = f"{subject}\n{body}"
    # Table layouts put labels and values on separate lines ("| $140.59DR |").
    flat = re.sub(r"[|\s]+", " ", text)
    amount = next((_money(m.group(1)) for p in AMOUNT_DUE if (m := p.search(flat))), None)
    due = next((d for p in DUE_DATE if (m := p.search(flat)) and (d := _date(m.group(1)))), None)
    fee_match = LATE_FEE.search(flat)
    return BillDetails(amount, due, _money(fee_match.group(1)) if fee_match else None)
