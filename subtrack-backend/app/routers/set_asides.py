"""Money set aside each pay, and spends logged against what's free to spend."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import verify_token
from app.models import Category, SetAside, Transaction, TransactionKind, TransactionSource
from app.services.pay_cycles import pay_cycles
from app.services.product_events import record
from app.services.safe_to_spend import _user_zone, safe_to_spend
from app.services.transactions import apply_conversion, base_currency_for

router = APIRouter(tags=["set asides"])

MAX_SET_ASIDES = 12
SupportedCurrency = Literal["AUD", "USD", "GBP", "SGD", "EUR", "JPY"]
Money = Field(gt=0, le=Decimal("1000000"), max_digits=12, decimal_places=2)


class SetAsideCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["save", "pot"]
    name: str = Field(min_length=1, max_length=80)
    amount_per_pay: Decimal = Money
    target_amount: Decimal | None = Field(default=None, gt=0, le=Decimal("1000000"), max_digits=12, decimal_places=2)


class SetAsideUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=80)
    amount_per_pay: Decimal | None = Field(default=None, gt=0, le=Decimal("1000000"), max_digits=12, decimal_places=2)
    target_amount: Decimal | None = Field(default=None, gt=0, le=Decimal("1000000"), max_digits=12, decimal_places=2)


class SpendCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    amount: Decimal = Money
    currency: SupportedCurrency | None = None
    set_aside_id: UUID | None = None
    category: Category = Category.other


def _owned(db: Session, user_id: str, set_aside_id: UUID) -> SetAside:
    row = db.get(SetAside, set_aside_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(404, "Set-aside not found")
    return row


def _payload(row: SetAside) -> dict:
    return {
        "id": str(row.id),
        "kind": row.kind,
        "name": row.name,
        "amount_per_pay": float(row.amount_per_pay),
        "currency": row.currency,
        "target_amount": float(row.target_amount) if row.target_amount is not None else None,
    }


@router.get("/set-asides")
def list_set_asides(user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    rows = db.query(SetAside).filter(SetAside.user_id == user_id).order_by(SetAside.created_at, SetAside.id)
    return [_payload(row) for row in rows]


@router.post("/set-asides", status_code=201)
def create_set_aside(body: SetAsideCreate, user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    if db.query(SetAside).filter(SetAside.user_id == user_id).count() >= MAX_SET_ASIDES:
        raise HTTPException(422, f"You can have up to {MAX_SET_ASIDES} set-asides.")
    row = SetAside(
        user_id=user_id,
        kind=body.kind,
        name=body.name,
        amount_per_pay=body.amount_per_pay,
        currency=base_currency_for(db, user_id),
        target_amount=body.target_amount if body.kind == "save" else None,
    )
    db.add(row)
    db.commit()
    return _payload(row)


@router.patch("/set-asides/{set_aside_id}")
def update_set_aside(
    set_aside_id: UUID, body: SetAsideUpdate, user_id: str = Depends(verify_token), db: Session = Depends(get_db),
):
    row = _owned(db, user_id, set_aside_id)
    changes = body.model_dump(exclude_unset=True)
    for field in ("name", "amount_per_pay"):
        if field in changes:
            if changes[field] is None:
                raise HTTPException(422, f"{field} cannot be cleared")
            setattr(row, field, changes[field])
    if "target_amount" in changes and row.kind == "save":
        row.target_amount = changes["target_amount"]
    db.commit()
    return _payload(row)


@router.delete("/set-asides/{set_aside_id}", status_code=204)
def delete_set_aside(set_aside_id: UUID, user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    row = _owned(db, user_id, set_aside_id)
    # Spends keep their history but stop using up a pot that no longer exists.
    db.query(Transaction).filter(
        Transaction.user_id == user_id, Transaction.set_aside_id == row.id,
    ).update({Transaction.set_aside_id: None}, synchronize_session=False)
    db.delete(row)
    db.commit()


@router.post("/safe-to-spend/spends", status_code=201)
def log_spend(body: SpendCreate, user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    """Record money spent today; it comes off a pot, or off what's free to spend."""
    if body.set_aside_id is not None:
        pot = _owned(db, user_id, body.set_aside_id)
        if pot.kind != "pot":
            raise HTTPException(422, "Spends can only come out of a spending budget.")
    if body.category == Category.income:
        raise HTTPException(422, "A spend can't use the income category.")
    row = Transaction(
        user_id=user_id,
        kind=TransactionKind.expense.value,
        name=body.name,
        amount=body.amount,
        currency=body.currency or base_currency_for(db, user_id),
        category=body.category,
        occurred_on=datetime.now(_user_zone(db, user_id)).date(),
        source=TransactionSource.manual.value,
        set_aside_id=body.set_aside_id,
    )
    apply_conversion(db, row, base_currency_for(db, user_id))
    db.add(row)
    db.commit()
    record(db, user_id, "spend_logged")
    return safe_to_spend(db, user_id)


class IncomeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    amount: Decimal = Money
    currency: SupportedCurrency | None = None


@router.post("/safe-to-spend/incomes", status_code=201)
def log_income(body: IncomeCreate, user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    """Record money received today on top of usual pay; it adds to this pay cycle only."""
    row = Transaction(
        user_id=user_id,
        kind=TransactionKind.income.value,
        name=body.name,
        amount=body.amount,
        currency=body.currency or base_currency_for(db, user_id),
        category=Category.income,
        occurred_on=datetime.now(_user_zone(db, user_id)).date(),
        source=TransactionSource.manual.value,
    )
    apply_conversion(db, row, base_currency_for(db, user_id))
    db.add(row)
    db.commit()
    record(db, user_id, "income_logged")
    return safe_to_spend(db, user_id)


class SpendUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    amount: Decimal | None = Field(default=None, gt=0, le=Decimal("1000000"), max_digits=12, decimal_places=2)
    category: Category | None = None
    set_aside_id: UUID | None = None


@router.patch("/safe-to-spend/spends/{spend_id}")
def edit_spend(
    spend_id: UUID, body: SpendUpdate, user_id: str = Depends(verify_token), db: Session = Depends(get_db),
):
    """Fix a logged spend or extra income: its name, amount, category or budget."""
    row = db.get(Transaction, spend_id)
    if row is None or row.user_id != user_id or row.recurring_payment_id is not None:
        raise HTTPException(404, "Spend not found")
    is_income = row.kind == TransactionKind.income.value
    if is_income and ({"category", "set_aside_id"} & body.model_fields_set):
        raise HTTPException(422, "Extra income only has a name and an amount.")
    if body.category == Category.income:
        raise HTTPException(422, "A spend can't use the income category.")
    if body.set_aside_id is not None and _owned(db, user_id, body.set_aside_id).kind != "pot":
        raise HTTPException(422, "Spends can only come out of a spending budget.")
    if body.name is not None:
        row.name = body.name
    if body.amount is not None:
        row.amount = body.amount
        apply_conversion(db, row, base_currency_for(db, user_id))
    if body.category is not None:
        row.category = body.category
    if "set_aside_id" in body.model_fields_set:
        row.set_aside_id = body.set_aside_id
    db.commit()
    return safe_to_spend(db, user_id)


@router.delete("/safe-to-spend/spends/{spend_id}")
def undo_spend(spend_id: UUID, user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    row = db.get(Transaction, spend_id)
    if row is None or row.user_id != user_id or row.recurring_payment_id is not None:
        raise HTTPException(404, "Spend not found")
    db.delete(row)
    db.commit()
    return safe_to_spend(db, user_id)


@router.get("/safe-to-spend/cycles")
def list_pay_cycles(
    count: int = Query(default=6, ge=1, le=26),
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """This pay cycle and earlier ones: pots planned against spent, savings and other spends."""
    return pay_cycles(db, user_id, count=count)
