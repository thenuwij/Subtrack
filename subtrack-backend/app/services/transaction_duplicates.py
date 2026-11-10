"""Flag a new expense or income entry that may already be recorded.

The check is deliberately simple and explainable: same kind of name, a similar
amount in the same currency, and a close date. It only suggests; the user
decides whether to keep or remove the entry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import PaymentStatus, Subscription, Transaction

DATE_WINDOW_DAYS = 3
AMOUNT_TOLERANCE = Decimal("0.05")
AMOUNT_FLOOR = Decimal("1.00")
NAME_SIMILARITY = 0.8
MAX_MATCHES = 5


@dataclass(frozen=True)
class PossibleDuplicate:
    kind: Literal["transaction", "payment"]
    id: UUID
    name: str
    amount: Decimal
    currency: str
    occurred_on: date | None


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def names_match(first: str, second: str) -> bool:
    a, b = _normalise(first), _normalise(second)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    return SequenceMatcher(None, a, b).ratio() >= NAME_SIMILARITY


def amounts_match(first: Decimal, second: Decimal) -> bool:
    allowed = max(AMOUNT_FLOOR, max(first, second) * AMOUNT_TOLERANCE)
    return abs(first - second) <= allowed


def find_possible_duplicates(
    db: Session,
    user_id: str,
    *,
    name: str,
    amount: Decimal,
    currency: str,
    occurred_on: date,
    exclude_id: UUID | None = None,
) -> list[PossibleDuplicate]:
    """Return recorded entries and tracked payments that look like this one."""
    window = timedelta(days=DATE_WINDOW_DAYS)
    nearby = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.currency == currency,
        Transaction.occurred_on.between(occurred_on - window, occurred_on + window),
    )
    if exclude_id is not None:
        nearby = nearby.filter(Transaction.id != exclude_id)

    matches = [
        PossibleDuplicate("transaction", row.id, row.name, Decimal(row.amount), row.currency, row.occurred_on)
        for row in nearby.order_by(Transaction.occurred_on, Transaction.id).all()
        if names_match(name, row.name) and amounts_match(amount, Decimal(row.amount))
    ]

    payments = db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.is_active == True,  # noqa: E712
        Subscription.status.in_([PaymentStatus.active.value, PaymentStatus.cancelling.value]),
        Subscription.currency == currency,
    ).order_by(Subscription.name, Subscription.id).all()
    matches.extend(
        PossibleDuplicate("payment", row.id, row.name, Decimal(str(row.amount)), row.currency, None)
        for row in payments
        if names_match(name, row.name) and amounts_match(amount, Decimal(str(row.amount)))
    )
    return matches[:MAX_MATCHES]
