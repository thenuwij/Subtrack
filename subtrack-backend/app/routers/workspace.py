from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import verify_token
from app.models import Goal, Subscription, WorkspacePage
from app.services.features import feature_enabled
from app.services.workspace_blocks import (
    Block,
    GoalProgressBlock,
    PageBlocks,
    PaymentListBlock,
    blocks_to_json,
    validate_blocks,
)
from app.services.workspace_data import resolve_page_blocks
from app.services.workspace_templates import TEMPLATES, TemplateId

router = APIRouter(prefix="/workspace", tags=["workspace"])

WORKSPACE_OFF = "Custom workspace is turned off in Settings."
MAX_PAGES_PER_USER = 50
MAX_POSITION = 10_000
PAGE_LIMIT_REACHED = f"You can have up to {MAX_PAGES_PER_USER} workspace pages"


class PageCreate(BaseModel):
    """A page starts from a template's blocks, explicit blocks, or both (explicit blocks win)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=120)
    template_id: Optional[TemplateId] = None
    blocks: Optional[PageBlocks] = None

    @model_validator(mode="after")
    def has_a_layout(self):
        if self.template_id is None and self.blocks is None:
            raise ValueError("Choose a template or add at least one block")
        return self


class PageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    blocks: Optional[PageBlocks] = None
    position: Optional[int] = Field(default=None, ge=0, le=MAX_POSITION)

    @model_validator(mode="after")
    def fields_cannot_be_cleared(self):
        cleared = sorted(field for field in self.model_fields_set if getattr(self, field) is None)
        if cleared:
            raise ValueError(f"These fields cannot be cleared: {', '.join(cleared)}")
        return self


def page_summary(page: WorkspacePage) -> dict:
    return {
        "id": str(page.id),
        "title": page.title,
        "template_id": page.template_id,
        "block_count": len(page.blocks),
        "position": page.position,
        "updated_at": page.updated_at.isoformat() if page.updated_at else None,
    }


def page_payload(page: WorkspacePage) -> dict:
    return {
        "id": str(page.id),
        "title": page.title,
        "template_id": page.template_id,
        "blocks": page.blocks,
        "position": page.position,
        "created_at": page.created_at.isoformat() if page.created_at else None,
        "updated_at": page.updated_at.isoformat() if page.updated_at else None,
    }


def _require_workspace(db: Session, user_id: str) -> None:
    if not feature_enabled(db, user_id, "workspace"):
        raise HTTPException(status_code=403, detail=WORKSPACE_OFF)


def _owned_page(db: Session, user_id: str, page_id: UUID, *, for_update: bool = False) -> WorkspacePage:
    query = db.query(WorkspacePage).filter(WorkspacePage.id == page_id, WorkspacePage.user_id == user_id)
    if for_update:
        query = query.with_for_update()
    page = query.first()
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


def _require_owned_ids(db: Session, user_id: str, model: type, ids: set[UUID], not_found: str) -> None:
    if not ids:
        return
    owned = db.query(model.id).filter(model.user_id == user_id, model.id.in_(ids)).count()
    if owned != len(ids):
        raise HTTPException(status_code=404, detail=not_found)


def _require_owned_references(db: Session, user_id: str, blocks: list[Block]) -> None:
    """Payments and goals a block points at must be the user's own when the page is saved."""
    payment_ids = {
        payment_id
        for block in blocks
        if isinstance(block, PaymentListBlock)
        for payment_id in block.payment_ids or ()
    }
    goal_ids = {
        goal_id
        for block in blocks
        if isinstance(block, GoalProgressBlock)
        for goal_id in block.goal_ids or ()
    }
    _require_owned_ids(db, user_id, Subscription, payment_ids, "Payment not found")
    _require_owned_ids(db, user_id, Goal, goal_ids, "Goal not found")


def user_pages(db: Session, user_id: str) -> list[WorkspacePage]:
    return (
        db.query(WorkspacePage)
        .filter(WorkspacePage.user_id == user_id)
        .order_by(WorkspacePage.position, WorkspacePage.created_at, WorkspacePage.id)
        .all()
    )


def add_page(
    db: Session,
    user_id: str,
    title: str,
    template_id: Optional[TemplateId],
    blocks: Optional[list[Block]],
) -> WorkspacePage:
    """Add a page within the page limit, checking every id its blocks point at; the caller commits."""
    page_count, last_position = (
        db.query(func.count(WorkspacePage.id), func.max(WorkspacePage.position))
        .filter(WorkspacePage.user_id == user_id)
        .one()
    )
    if page_count >= MAX_PAGES_PER_USER:
        raise HTTPException(status_code=409, detail=PAGE_LIMIT_REACHED)
    if blocks is None:
        blocks = validate_blocks(list(TEMPLATES[template_id].blocks))
    _require_owned_references(db, user_id, blocks)
    page = WorkspacePage(
        user_id=user_id,
        title=title,
        template_id=template_id,
        blocks=blocks_to_json(blocks),
        position=min((last_position if last_position is not None else -1) + 1, MAX_POSITION),
    )
    db.add(page)
    db.flush()
    return page


@router.get("/templates")
def list_templates(
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    _require_workspace(db, user_id)
    return [
        {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "block_types": [block["type"] for block in template.blocks],
        }
        for template in TEMPLATES.values()
    ]


@router.get("/pages")
def list_pages(
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    _require_workspace(db, user_id)
    return [page_summary(page) for page in user_pages(db, user_id)]


@router.post("/pages", status_code=201)
def create_page(
    data: PageCreate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    _require_workspace(db, user_id)
    page = add_page(db, user_id, data.title, data.template_id, data.blocks)
    db.commit()
    db.refresh(page)
    return page_payload(page)


@router.get("/pages/{page_id}")
def get_page(
    page_id: UUID,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    _require_workspace(db, user_id)
    return page_payload(_owned_page(db, user_id, page_id))


@router.get("/pages/{page_id}/data")
def get_page_data(
    page_id: UUID,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Each block's live data in page order; a block that fails carries its own error."""
    _require_workspace(db, user_id)
    page = _owned_page(db, user_id, page_id)
    return {"id": str(page.id), "title": page.title, "blocks": resolve_page_blocks(db, user_id, page.blocks)}


@router.patch("/pages/{page_id}")
def update_page(
    page_id: UUID,
    data: PageUpdate,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
):
    _require_workspace(db, user_id)
    page = _owned_page(db, user_id, page_id)
    if data.blocks is not None:
        _require_owned_references(db, user_id, data.blocks)
        page.blocks = blocks_to_json(data.blocks)
    if data.title is not None:
        page.title = data.title
    if data.position is not None:
        page.position = data.position
    db.commit()
    db.refresh(page)
    return page_payload(page)


@router.delete("/pages/{page_id}", status_code=204)
def delete_page(
    page_id: UUID,
    user_id: str = Depends(verify_token),
    db: Session = Depends(get_db),
) -> None:
    _require_workspace(db, user_id)
    db.delete(_owned_page(db, user_id, page_id))
    db.commit()
