import time
from collections import defaultdict, deque
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import verify_token
from app.models import (
    Category,
    Subscription,
    Transaction,
    TransactionKind,
    TransactionSource,
)
from app.services.payment_charges import PaymentCharge, charged_payment_ids, month_payment_charges
from app.services.safe_to_spend import _user_zone
from app.services.transaction_parse import MAX_TEXT, ParseError, parse_transactions
from app.services.transaction_duplicates import find_possible_duplicates
from app.services.transactions import (
    MONTH_ROW_LIMIT,
    apply_conversion,
    base_currency_for,
    month_summary,
    month_transactions,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])

MAX_AMOUNT = Decimal("1000000")
EARLIEST_DATE = date(2000, 1, 1)
LATEST_DATE = date(2100, 12, 31)
MONTH_PATTERN = r"^(20\d\d|2100)-(0[1-9]|1[0-2])$"
SupportedCurrency = Literal["AUD", "USD", "GBP", "SGD", "EUR", "JPY"]


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    kind: TransactionKind
    name: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0, le=MAX_AMOUNT, decimal_places=2)
    currency: SupportedCurrency
    category: Category = Category.other
    occurred_on: Optional[date] = Field(default=None, ge=EARLIEST_DATE, le=LATEST_DATE)
    note: Optional[str] = Field(default=None, max_length=500)
    recurring_payment_id: Optional[UUID] = None


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    kind: Optional[TransactionKind] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    amount: Optional[Decimal] = Field(default=None, gt=0, le=MAX_AMOUNT, decimal_places=2)
    currency: Optional[SupportedCurrency] = None
    category: Optional[Category] = None
    occurred_on: Optional[date] = Field(default=None, ge=EARLIEST_DATE, le=LATEST_DATE)
    note: Optional[str] = Field(default=None, max_length=500)
    recurring_payment_id: Optional[UUID] = None

    @model_validator(mode="after")
    def required_fields_cannot_be_cleared(self):
        clearable = {"note", "recurring_payment_id"}
        cleared = sorted(
            field for field in self.model_fields_set - clearable if getattr(self, field) is None
        )
        if cleared:
            raise ValueError(f"These fields cannot be cleared: {', '.join(cleared)}")
        return self


PARSE_CALLS_PER_MINUTE = 10
_parse_calls: dict[str, deque[float]] = defaultdict(deque)


def _enforce_parse_rate_limit(user_id: str) -> None:
    """Per-process sliding window; the agent limiter counts chat rows, which parsing never writes."""
    now = time.monotonic()
    calls = _parse_calls[user_id]
    while calls and now - calls[0] >= 60:
        calls.popleft()
    if len(calls) >= PARSE_CALLS_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a minute and try again.",
            headers={"Retry-After": "60"},
        )
    calls.append(now)


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=MAX_TEXT)


def transaction_payload(row: Transaction) -> dict:
    return {
        "id": str(row.id),
        "kind": row.kind,
        "name": row.name,
        "amount": float(row.amount),
        "currency": row.currency,
        "base_amount": float(row.base_amount) if row.base_amount is not None else None,
        "base_currency": row.base_currency,
        "rate_as_of": row.rate_as_of.isoformat() if row.rate_as_of else None,
        "category": row.category.value if isinstance(row.category, Category) else row.category,
        "occurred_on": row.occurred_on.isoformat(),
        "note": row.note,
        "source": row.source,
        "recurring_payment_id": str(row.recurring_payment_id) if row.recurring_payment_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def payment_charge_payload(charge: PaymentCharge, base: str) -> dict:
    """A read-only expense row for one tracked payment charge."""
    return {
        "id": charge.row_id,
        "kind": TransactionKind.expense.value,
        "name": charge.name,
        "amount": float(charge.amount),
        "currency": charge.currency,
        "base_amount": float(charge.base_amount) if charge.base_amount is not None else None,
        "base_currency": base if charge.base_amount is not None else None,
        "rate_as_of": None,
        "category": charge.category,
        "occurred_on": charge.occurred_on.isoformat(),
        "note": None,
        "source": "payment",
        "recurring_payment_id": charge.payment_id,
        "read_only": True,
        "counted_in_payment": False,
        "created_at": None,
        "updated_at": None,
    }


def _owned_transaction(db: Session, user_id: str, transaction_id: UUID) -> Transaction:
    row = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == user_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return row


def _require_owned_payment(db: Session, user_id: str, payment_id: UUID) -> None:
    exists = db.query(Subscription.id).filter(
        Subscription.id == payment_id,
        Subscription.user_id == user_id,
    ).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="Recurring payment not found")


def _year_month(db: Session, user_id: str, month: str | None) -> tuple[int, int]:
    if month is None:
        today = datetime.now(_user_zone(db, user_id)).date()
        return today.year, today.month
    year, month_number = month.split("-")
    return int(year), int(month_number)


@router.get("")
def list_transactions(
    month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    kind: TransactionKind | None = None,
    category: Category | None = None,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    year, month_number = _year_month(db, user_id, month)
    rows = month_transactions(
        db, user_id, year, month_number, kind=kind, category=category, limit=MONTH_ROW_LIMIT,
    )
    charges = month_payment_charges(db, user_id, year, month_number)
    charged_ids = charged_payment_ids(charges)
    entries = [
        {
            **transaction_payload(row),
            "read_only": False,
            "counted_in_payment": (
                row.kind == TransactionKind.expense.value
                and row.recurring_payment_id is not None
                and str(row.recurring_payment_id) in charged_ids
            ),
        }
        for row in rows
    ]
    if kind in (None, TransactionKind.expense):
        base = base_currency_for(db, user_id)
        entries.extend(
            payment_charge_payload(charge, base)
            for charge in charges
            if category is None or charge.category == category.value
        )
    entries.sort(key=lambda entry: entry["occurred_on"], reverse=True)
    return entries


@router.get("/summary")
def get_transaction_summary(
    month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    year, month_number = _year_month(db, user_id, month)
    return month_summary(db, user_id, year, month_number)


@router.post("/parse")
def parse_transaction_text(
    data: ParseRequest,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Suggest drafts from free text. Nothing is saved."""
    _enforce_parse_rate_limit(user_id)
    today = datetime.now(_user_zone(db, user_id)).date()
    try:
        drafts = parse_transactions(data.text, today, base_currency_for(db, user_id))
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "drafts": [
            {
                "kind": draft.kind.value,
                "amount": float(draft.amount),
                "currency": draft.currency,
                "category": "income" if draft.kind == TransactionKind.income else draft.category.value,
                "name": draft.name,
                "occurred_on": draft.occurred_on.isoformat(),
                "note": draft.note,
            }
            for draft in drafts
        ]
    }


@router.post("", status_code=201)
def create_transaction(
    data: TransactionCreate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    if data.recurring_payment_id is not None:
        _require_owned_payment(db, user_id, data.recurring_payment_id)
    row = Transaction(
        user_id=user_id,
        kind=data.kind.value,
        name=data.name,
        amount=data.amount,
        currency=data.currency,
        category=data.category,
        occurred_on=data.occurred_on or datetime.now(_user_zone(db, user_id)).date(),
        note=data.note,
        source=TransactionSource.manual.value,
        recurring_payment_id=data.recurring_payment_id,
    )
    apply_conversion(db, row, base_currency_for(db, user_id))
    db.add(row)
    db.commit()
    db.refresh(row)

    duplicates = find_possible_duplicates(
        db, user_id,
        name=row.name, amount=Decimal(row.amount), currency=row.currency,
        occurred_on=row.occurred_on, exclude_id=row.id,
    )
    return {
        **transaction_payload(row),
        "possible_duplicates": [
            {
                "kind": match.kind,
                "id": str(match.id),
                "name": match.name,
                "amount": float(match.amount),
                "currency": match.currency,
                "occurred_on": match.occurred_on.isoformat() if match.occurred_on else None,
            }
            for match in duplicates
        ],
    }


@router.patch("/{transaction_id}")
def update_transaction(
    transaction_id: UUID,
    data: TransactionUpdate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    row = _owned_transaction(db, user_id, transaction_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("recurring_payment_id") is not None:
        _require_owned_payment(db, user_id, changes["recurring_payment_id"])
    if "kind" in changes:
        changes["kind"] = changes["kind"].value
    money_changed = any(
        field in changes and changes[field] != getattr(row, field)
        for field in ("amount", "currency")
    )
    for field, value in changes.items():
        setattr(row, field, value)
    if money_changed:
        apply_conversion(db, row, base_currency_for(db, user_id))
    db.commit()
    db.refresh(row)
    return transaction_payload(row)


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(
    transaction_id: UUID,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
) -> None:
    row = _owned_transaction(db, user_id, transaction_id)
    db.delete(row)
    db.commit()
