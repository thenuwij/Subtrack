"""User-scoped assistant reads for workspace pages, and the advice check on page text.

The reads reuse the workspace router, so the assistant sees the same templates
and pages the Workspace shows. Pages are only ever built from the fixed blocks.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.policy import check_user_text
from app.routers.workspace import WORKSPACE_OFF, list_templates, page_payload, user_pages
from app.services.features import feature_enabled

WORKSPACE_FEATURE = "workspace"
WORKSPACE_OFF_ERROR = {"error": WORKSPACE_OFF}
WORKSPACE_TOOLS = frozenset({
    "list_workspace_templates",
    "list_workspace_pages",
    "propose_create_workspace_page",
    "propose_update_workspace_page",
    "propose_remove_workspace_page",
})
PAGE_TEXT_TOOLS = frozenset({"propose_create_workspace_page", "propose_update_workspace_page"})


def workspace_enabled(db: Session, user_id: str) -> bool:
    return feature_enabled(db, user_id, WORKSPACE_FEATURE)


def workspace_templates(db: Session, user_id: str) -> dict:
    return {"templates": list_templates(user_id=user_id, db=db)}


def workspace_pages(db: Session, user_id: str) -> dict:
    """Each page with its current blocks, which a full-blocks update has to start from."""
    return {"pages": [page_payload(page) for page in user_pages(db, user_id)]}


def _page_texts(tool_input: dict) -> list[str]:
    """The user-visible text the AI wrote: page and block titles, checklist items, notes, cost labels."""
    texts = [tool_input.get("title")]
    blocks = tool_input.get("blocks")
    for block in blocks if isinstance(blocks, list) else ():
        if not isinstance(block, dict):
            continue
        texts.append(block.get("title"))
        if block.get("type") == "notes":
            texts.append(block.get("text"))
        items = block.get("items")
        for item in items if isinstance(items, list) else ():
            if isinstance(item, dict):
                texts.extend((item.get("text"), item.get("label")))
    return [text for text in texts if isinstance(text, str)]


def advice_refusal(tool_input: dict) -> dict | None:
    """A plain refusal when AI-written page text contains financial-product advice."""
    for text in _page_texts(tool_input):
        phrase = check_user_text(text)
        if phrase:
            return {
                "error": (
                    f'Workspace pages can\'t include financial-product advice ("{phrase}"). '
                    "Pages track and organise the user's own money only."
                )
            }
    return None
