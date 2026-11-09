from collections.abc import Sequence
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import verify_token
from app.models import Goal, GoalContribution, TransactionSource
from app.routers.transactions import EARLIEST_DATE, LATEST_DATE, MAX_AMOUNT, SupportedCurrency
from app.services.goals import goal_progress
from app.services.safe_to_spend import _user_zone

router = APIRouter(prefix="/goals", tags=["goals"])

NEGATIVE_BALANCE = "You can't take out more than this goal has saved"


class GoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    name: str = Field(min_length=1, max_length=120)
    target_amount: Decimal = Field(gt=0, le=MAX_AMOUNT, decimal_places=2)
    currency: SupportedCurrency
    target_date: Optional[date] = Field(default=None, ge=EARLIEST_DATE, le=LATEST_DATE)


class GoalUpdate(BaseModel):
    """Currency is fixed at creation because contributions are stored in it."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    target_amount: Optional[Decimal] = Field(default=None, gt=0, le=MAX_AMOUNT, decimal_places=2)
    target_date: Optional[date] = Field(default=None, ge=EARLIEST_DATE, le=LATEST_DATE)
    archived: Optional[bool] = None

    @model_validator(mode="after")
    def required_fields_cannot_be_cleared(self):
        cleared = sorted(
            field for field in self.model_fields_set - {"target_date"} if getattr(self, field) is None
        )
        if cleared:
            raise ValueError(f"These fields cannot be cleared: {', '.join(cleared)}")
        return self


class ContributionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    amount: Decimal = Field(ge=-MAX_AMOUNT, le=MAX_AMOUNT, decimal_places=2)
    occurred_on: Optional[date] = Field(default=None, ge=EARLIEST_DATE, le=LATEST_DATE)
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("amount")
    @classmethod
    def amount_is_not_zero(cls, amount: Decimal) -> Decimal:
        if amount == 0:
            raise ValueError("Amount cannot be zero")
        return amount


def contribution_payload(row: GoalContribution) -> dict:
    return {
        "id": str(row.id),
        "goal_id": str(row.goal_id),
        "amount": float(row.amount),
        "occurred_on": row.occurred_on.isoformat(),
        "note": row.note,
        "source": row.source,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _saved(contributions: Sequence[GoalContribution]) -> Decimal:
    return sum((Decimal(row.amount) for row in contributions), Decimal("0"))


def goal_payload(goal: Goal, contributions: Sequence[GoalContribution], today: date) -> dict:
    return {
        "id": str(goal.id),
        "name": goal.name,
        "target_amount": float(goal.target_amount),
        "currency": goal.currency,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "archived_at": goal.archived_at.isoformat() if goal.archived_at else None,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
        "updated_at": goal.updated_at.isoformat() if goal.updated_at else None,
        **goal_progress(goal, _saved(contributions), today),
        "contributions": [contribution_payload(row) for row in contributions],
    }


def _today(db: Session, user_id: str) -> date:
    return datetime.now(_user_zone(db, user_id)).date()


def _owned_goal(db: Session, user_id: str, goal_id: UUID) -> Goal:
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user_id).first()
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


def _contributions(db: Session, user_id: str, goal_ids: Sequence[UUID]) -> list[GoalContribution]:
    if not goal_ids:
        return []
    return (
        db.query(GoalContribution)
        .filter(GoalContribution.user_id == user_id, GoalContribution.goal_id.in_(goal_ids))
        .order_by(GoalContribution.occurred_on.desc(), GoalContribution.created_at.desc(), GoalContribution.id)
        .all()
    )


def _goal_response(db: Session, user_id: str, goal: Goal) -> dict:
    return goal_payload(goal, _contributions(db, user_id, [goal.id]), _today(db, user_id))


@router.get("")
def list_goals(
    include_archived: bool = False,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    query = db.query(Goal).filter(Goal.user_id == user_id)
    if not include_archived:
        query = query.filter(Goal.archived_at.is_(None))
    goals = query.order_by(Goal.created_at, Goal.id).all()
    by_goal: dict[UUID, list[GoalContribution]] = {goal.id: [] for goal in goals}
    for row in _contributions(db, user_id, list(by_goal)):
        by_goal[row.goal_id].append(row)
    today = _today(db, user_id)
    return [goal_payload(goal, by_goal[goal.id], today) for goal in goals]


@router.post("", status_code=201)
def create_goal(
    data: GoalCreate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    goal = Goal(user_id=user_id, **data.model_dump())
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal_payload(goal, [], _today(db, user_id))


@router.patch("/{goal_id}")
def update_goal(
    goal_id: UUID,
    data: GoalUpdate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    goal = _owned_goal(db, user_id, goal_id)
    changes = data.model_dump(exclude_unset=True)
    if "archived" in changes:
        archived = changes.pop("archived")
        if archived and goal.archived_at is None:
            goal.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
        elif not archived:
            goal.archived_at = None
    for field, value in changes.items():
        setattr(goal, field, value)
    db.commit()
    db.refresh(goal)
    return _goal_response(db, user_id, goal)


@router.delete("/{goal_id}", status_code=204)
def delete_goal(
    goal_id: UUID,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
) -> None:
    goal = _owned_goal(db, user_id, goal_id)
    # Deleted explicitly too, because SQLite does not enforce the cascade by default.
    db.query(GoalContribution).filter(
        GoalContribution.goal_id == goal.id, GoalContribution.user_id == user_id,
    ).delete(synchronize_session=False)
    db.delete(goal)
    db.commit()


@router.post("/{goal_id}/contributions", status_code=201)
def add_contribution(
    goal_id: UUID,
    data: ContributionCreate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    goal = _owned_goal(db, user_id, goal_id)
    if _saved(_contributions(db, user_id, [goal.id])) + data.amount < 0:
        raise HTTPException(status_code=409, detail=NEGATIVE_BALANCE)
    row = GoalContribution(
        goal_id=goal.id,
        user_id=user_id,
        amount=data.amount,
        occurred_on=data.occurred_on or _today(db, user_id),
        note=data.note,
        source=TransactionSource.manual.value,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {**contribution_payload(row), "goal": _goal_response(db, user_id, goal)}


@router.delete("/{goal_id}/contributions/{contribution_id}", status_code=204)
def delete_contribution(
    goal_id: UUID,
    contribution_id: UUID,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
) -> None:
    goal = _owned_goal(db, user_id, goal_id)
    contributions = _contributions(db, user_id, [goal.id])
    row = next((item for item in contributions if item.id == contribution_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Contribution not found")
    if _saved(contributions) - Decimal(row.amount) < 0:
        raise HTTPException(status_code=409, detail=NEGATIVE_BALANCE)
    db.delete(row)
    db.commit()
