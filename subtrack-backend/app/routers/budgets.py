from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import verify_token
from app.models import Budget, Category
from app.routers.transactions import MAX_AMOUNT, MONTH_PATTERN, _year_month
from app.services.budgets import budget_status
from app.services.transactions import base_currency_for

router = APIRouter(prefix="/budgets", tags=["budgets"])

DUPLICATE_CATEGORY = "There is already a budget for this category"


class BudgetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    category: Category
    monthly_limit: Decimal = Field(gt=0, le=MAX_AMOUNT, decimal_places=2)


class BudgetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    category: Optional[Category] = None
    monthly_limit: Optional[Decimal] = Field(default=None, gt=0, le=MAX_AMOUNT, decimal_places=2)


def budget_payload(budget: Budget) -> dict:
    return {
        "id": str(budget.id),
        "category": budget.category.value if isinstance(budget.category, Category) else budget.category,
        "monthly_limit": float(budget.monthly_limit),
        "currency": budget.currency,
        "created_at": budget.created_at.isoformat() if budget.created_at else None,
        "updated_at": budget.updated_at.isoformat() if budget.updated_at else None,
    }


def _owned_budget(db: Session, user_id: str, budget_id: UUID) -> Budget:
    budget = db.query(Budget).filter(Budget.id == budget_id, Budget.user_id == user_id).first()
    if budget is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


def _require_free_category(db: Session, user_id: str, category: Category, exclude_id: UUID | None = None) -> None:
    query = db.query(Budget.id).filter(Budget.user_id == user_id, Budget.category == category)
    if exclude_id is not None:
        query = query.filter(Budget.id != exclude_id)
    if query.first() is not None:
        raise HTTPException(status_code=409, detail=DUPLICATE_CATEGORY)


def _commit_budget(db: Session, budget: Budget) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_CATEGORY) from error
    db.refresh(budget)


@router.get("")
def get_budget_status(
    month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    year, month_number = _year_month(db, user_id, month)
    return budget_status(db, user_id, year, month_number)


@router.post("", status_code=201)
def create_budget(
    data: BudgetCreate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    _require_free_category(db, user_id, data.category)
    budget = Budget(
        user_id=user_id,
        category=data.category,
        monthly_limit=data.monthly_limit,
        currency=base_currency_for(db, user_id),
    )
    db.add(budget)
    _commit_budget(db, budget)
    return budget_payload(budget)


@router.patch("/{budget_id}")
def update_budget(
    budget_id: UUID,
    data: BudgetUpdate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    budget = _owned_budget(db, user_id, budget_id)
    if data.category is not None:
        _require_free_category(db, user_id, data.category, exclude_id=budget.id)
        budget.category = data.category
    if data.monthly_limit is not None:
        # A new limit is typed in today's base currency.
        budget.monthly_limit = data.monthly_limit
        budget.currency = base_currency_for(db, user_id)
    _commit_budget(db, budget)
    return budget_payload(budget)


@router.delete("/{budget_id}", status_code=204)
def delete_budget(
    budget_id: UUID,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
) -> None:
    budget = _owned_budget(db, user_id, budget_id)
    db.delete(budget)
    db.commit()
