"""The tracked payment charges dated in one calendar month.

Budgets and the Transactions list both read charges from here so the two
can never count a recurring payment differently. Dates and amounts come from
the shared calendar-month schedule; nothing here recomputes a recurrence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Category, Subscription

PAYMENT_MANUAL = "manual"


@dataclass(frozen=True)
class PaymentCharge:
    payment_id: str
    name: str
    occurred_on: date
    amount: Decimal
    currency: str
    base_amount: Decimal | None
    category: str
    is_extra: bool
    extra_id: str | None = None

    @property
    def row_id(self) -> str:
        suffix = f":extra:{self.extra_id}" if self.is_extra else ""
        return f"payment:{self.payment_id}:{self.occurred_on.isoformat()}{suffix}"


def _category_value(category: Category | str | None) -> str:
    if category is None:
        return Category.other.value
    return category.value if isinstance(category, Category) else category


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def month_payment_charges(db: Session, user_id: str, year: int, month: int) -> list[PaymentCharge]:
    """Every scheduled charge and logged extra for the user's payments in one month.

    Scheduled charges of manually paid payments are left out.

    ``base_amount`` is None when no valid shared rate exists; it is never 1:1.
    """
    from app.routers.subscriptions import get_calendar_month

    calendar_month = get_calendar_month(year=year, month=month, user_id=user_id, db=db)
    # A manual payment's scheduled charge is not money out until the user marks
    # it paid, which records a linked Transaction instead.
    manual_ids = {
        str(payment_id) for (payment_id,) in db.query(Subscription.id).filter(
            Subscription.user_id == user_id,
            Subscription.payment_method == PAYMENT_MANUAL,
        ).all()
    }
    charges = [
        PaymentCharge(
            payment_id=charge["id"],
            name=charge["name"],
            occurred_on=datetime.fromisoformat(charge["due_at"]).date(),
            amount=Decimal(str(charge["amount"])),
            currency=charge["currency"],
            base_amount=_decimal(charge.get("charge_amount_in_base")),
            category=_category_value(charge.get("category")),
            is_extra=False,
        )
        for charge in calendar_month["charges"]
        if charge["id"] not in manual_ids
    ]

    extras = calendar_month["extras"]
    if extras:
        rows = db.query(Subscription.id, Subscription.name, Subscription.category).filter(
            Subscription.user_id == user_id,
            Subscription.id.in_({UUID(extra["subscription_id"]) for extra in extras}),
        ).all()
        payments = {str(payment_id): (name, _category_value(category)) for payment_id, name, category in rows}
        for extra in extras:
            name, category = payments.get(extra["subscription_id"], ("Recurring payment", Category.other.value))
            charges.append(PaymentCharge(
                payment_id=extra["subscription_id"],
                name=name,
                occurred_on=datetime.fromisoformat(extra["charged_at"]).date(),
                amount=Decimal(str(extra["amount"])),
                currency=extra["currency"],
                base_amount=_decimal(extra["amount_in_base"]),
                category=category,
                is_extra=True,
                extra_id=extra["id"],
            ))
    return charges


def charged_payment_ids(charges: list[PaymentCharge]) -> set[str]:
    """Payments with a scheduled charge this month; a linked logged expense is the same money."""
    return {charge.payment_id for charge in charges if not charge.is_extra}
