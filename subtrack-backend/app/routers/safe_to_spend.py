from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import verify_token
from app.models import SafeToSpendProfile
from app.services.product_events import record
from app.services.safe_to_spend import can_i_afford, safe_to_spend

router = APIRouter(prefix="/safe-to-spend", tags=["safe-to-spend"])

MAX_FUTURE_PAYDAY_DAYS = 366


class SafeToSpendProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    balance: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    pay_amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    currency: Literal["AUD", "USD", "GBP", "SGD", "EUR", "JPY"] = "AUD"
    next_payday: date
    pay_interval_unit: Literal["week", "month"]
    pay_interval_count: int = Field(ge=1, le=12)
    buffer: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    payday_bills_after_pay: bool = False

    @model_validator(mode="after")
    def needs_balance_or_pay(self):
        if self.balance is None and self.pay_amount is None:
            raise ValueError("Enter today's balance or your usual pay.")
        return self


@router.get("")
def get_safe_to_spend(user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    record(db, user_id, "home_viewed")
    return safe_to_spend(db, user_id)


@router.get("/afford")
def get_can_i_afford(
    amount: Decimal = Query(gt=0, max_digits=12, decimal_places=2),
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    record(db, user_id, "afford_check")
    return can_i_afford(db, user_id, amount)


@router.put("/profile")
def put_profile(
    body: SafeToSpendProfileUpdate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if body.next_payday > now.date() + timedelta(days=MAX_FUTURE_PAYDAY_DAYS):
        raise HTTPException(status_code=422, detail="Next payday must be within the next year.")

    profile = db.get(SafeToSpendProfile, user_id)
    if profile is None:
        profile = SafeToSpendProfile(user_id=user_id)
        db.add(profile)
    balance_changed = body.balance is not None and (
        profile.balance_as_of is None
        or profile.balance != body.balance
        or profile.currency != body.currency
    )
    if body.balance is None:
        profile.balance_as_of = None
    elif balance_changed:
        profile.balance_as_of = now

    profile.balance = body.balance
    profile.pay_amount = body.pay_amount
    profile.currency = body.currency
    profile.pay_anchor_on = body.next_payday
    profile.pay_interval_unit = body.pay_interval_unit
    profile.pay_interval_count = body.pay_interval_count
    profile.buffer = body.buffer
    profile.payday_bills_after_pay = body.payday_bills_after_pay
    db.commit()
    if balance_changed:
        record(db, user_id, "balance_updated", now=now)
    return safe_to_spend(db, user_id, now=now)
