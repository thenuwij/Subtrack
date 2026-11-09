"""User-scoped assistant reads for budgets and savings goals.

Both tools reuse the services behind the REST API, so the assistant quotes the
same spent, left, saved and per-week figures the Goals and budgets page shows.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.spending import _month
from app.routers.goals import list_goals
from app.services.budgets import budget_status
from app.services.features import feature_enabled

GOALS_FEATURE = "goals"
GOALS_OFF = {"error": "Goals and budgets is turned off in Settings."}
GOALS_TOOLS = frozenset({
    "get_budget_status",
    "list_goals",
    "propose_set_budget",
    "propose_remove_budget",
    "propose_create_goal",
    "propose_update_goal",
    "propose_remove_goal",
    "propose_add_goal_contribution",
})


def goals_enabled(db: Session, user_id: str) -> bool:
    return feature_enabled(db, user_id, GOALS_FEATURE)


def budget_status_for_month(db: Session, user_id: str, tool_input: dict) -> dict:
    try:
        year, month = _month(db, user_id, tool_input)
    except ValueError as exc:
        return {"error": str(exc)}
    return budget_status(db, user_id, year, month)


def goals_with_progress(db: Session, user_id: str, tool_input: dict) -> dict:
    include_archived = tool_input.get("include_archived", False)
    if not isinstance(include_archived, bool):
        return {"error": "include_archived must be true or false"}
    return {"goals": list_goals(include_archived=include_archived, user_id=user_id, db=db)}
