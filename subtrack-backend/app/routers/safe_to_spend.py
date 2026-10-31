from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import verify_token
from app.models import SafeToSpendProfile
from app.services.safe_to_spend import can_i_afford, safe_to_spend

router = APIRouter(prefix="/safe-to-spend", tags=["safe-to-spend"])

MAX_FUTURE_PAYDAY_DAYS = 366


class SafeToSpendProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    balance: Decimal = Field(max_digits=12, decimal_places=2)
    currency: Literal["AUD", "USD", "GBP", "SGD", "EUR", "JPY"] = "AUD"
    next_payday: date
    pay_interval_unit: Literal["week", "month"]
    pay_interval_count: int = Field(ge=1, le=12)
    buffer: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)


@router.get("")
def get_safe_to_spend(user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    return safe_to_spend(db, user_id)


@router.get("/afford")
def get_can_i_afford(
    amount: Decimal = Query(gt=0, max_digits=12, decimal_places=2),
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
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
        profile = SafeToSpendProfile(user_id=user_id, balance_as_of=now)
        db.add(profile)
    elif profile.balance != body.balance or profile.currency != body.currency:
        profile.balance_as_of = now

    profile.balance = body.balance
    profile.currency = body.currency
    profile.pay_anchor_on = body.next_payday
    profile.pay_interval_unit = body.pay_interval_unit
    profile.pay_interval_count = body.pay_interval_count
    profile.buffer = body.buffer
    db.commit()
    return safe_to_spend(db, user_id, now=now)
