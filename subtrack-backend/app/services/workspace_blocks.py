"""The fixed set of blocks a workspace page can be built from.

A page stores only this layout; blocks read live data when shown. Every model
forbids unknown keys and bounds its strings and lists, because the assistant
will be limited to building pages from exactly these shapes.
"""

from decimal import Decimal
from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.models import Category, TransactionKind
from app.routers.transactions import MAX_AMOUNT, SupportedCurrency

MAX_BLOCKS_PER_PAGE = 20

TransactionRange = Literal["this_month", "last_month", "last_3_months"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class _Block(_Strict):
    title: Optional[str] = Field(default=None, min_length=1, max_length=80)


class PaymentListBlock(_Block):
    type: Literal["payment_list"]
    category: Optional[Category] = None
    payment_ids: Optional[list[UUID]] = Field(default=None, max_length=50)


class TransactionLogBlock(_Block):
    type: Literal["transaction_log"]
    kind: Optional[TransactionKind] = None
    category: Optional[Category] = None
    range: Optional[TransactionRange] = None


class BudgetBlock(_Block):
    type: Literal["budget"]
    categories: Optional[list[Category]] = Field(default=None, max_length=20)


class GoalProgressBlock(_Block):
    type: Literal["goal_progress"]
    goal_ids: Optional[list[UUID]] = Field(default=None, max_length=20)


class UpcomingPaymentsBlock(_Block):
    type: Literal["upcoming_payments"]
    days: int = Field(default=30, ge=7, le=90)


class SpendingTrendBlock(_Block):
    type: Literal["spending_trend"]
    months: int = Field(default=6, ge=3, le=12)
    category: Optional[Category] = None


class ChecklistItem(_Strict):
    text: str = Field(min_length=1, max_length=200)
    done: bool = False


class ChecklistBlock(_Block):
    type: Literal["checklist"]
    items: list[ChecklistItem] = Field(default_factory=list, max_length=50)


PersonName = Annotated[str, Field(min_length=1, max_length=60)]


class SharedCostItem(_Strict):
    label: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, le=MAX_AMOUNT, decimal_places=2)
    paid_by: PersonName
    split_between: list[PersonName] = Field(min_length=1, max_length=10)


class SharedCostsBlock(_Block):
    """Costs shared between people; no currency means the user's base currency."""

    type: Literal["shared_costs"]
    people: list[PersonName] = Field(default_factory=list, max_length=10)
    items: list[SharedCostItem] = Field(default_factory=list, max_length=50)
    currency: Optional[SupportedCurrency] = None

    @model_validator(mode="after")
    def items_only_name_listed_people(self):
        if len(set(self.people)) != len(self.people):
            raise ValueError("Each person can only be listed once")
        people = set(self.people)
        for item in self.items:
            if item.paid_by not in people:
                raise ValueError(f"{item.paid_by} is not one of the people on this block")
            if len(set(item.split_between)) != len(item.split_between):
                raise ValueError("Each person can only be in a split once")
            outsiders = sorted(set(item.split_between) - people)
            if outsiders:
                raise ValueError(f"Not people on this block: {', '.join(outsiders)}")
        return self


class NotesBlock(_Block):
    type: Literal["notes"]
    text: str = Field(default="", max_length=5000)


Block = Annotated[
    Union[
        PaymentListBlock,
        TransactionLogBlock,
        BudgetBlock,
        GoalProgressBlock,
        UpcomingPaymentsBlock,
        SpendingTrendBlock,
        ChecklistBlock,
        SharedCostsBlock,
        NotesBlock,
    ],
    Field(discriminator="type"),
]

PageBlocks = Annotated[list[Block], Field(min_length=1, max_length=MAX_BLOCKS_PER_PAGE)]

page_blocks_adapter: TypeAdapter[list[Block]] = TypeAdapter(PageBlocks)


def validate_blocks(raw: list[dict]) -> list[Block]:
    """Validate raw block dicts, raising pydantic.ValidationError if any is not allowed."""
    return page_blocks_adapter.validate_python(raw)


def blocks_to_json(blocks: list[Block]) -> list[dict]:
    """The stored form of a validated layout."""
    return page_blocks_adapter.dump_python(blocks, mode="json")
