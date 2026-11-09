"""Progress towards a savings goal and how much is needed to reach it in time."""

from __future__ import annotations

import math
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Literal

from app.models import Goal
from app.services.transactions import CENTS

GoalStatus = Literal["reached", "no_target_date", "on_the_way", "due_today", "target_date_passed"]

PERCENT_PLACES = Decimal("0.1")


def _round_up_cents(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_CEILING)


def _status(target_date: date | None, reached: bool, today: date) -> GoalStatus:
    if reached:
        return "reached"
    if target_date is None:
        return "no_target_date"
    if target_date > today:
        return "on_the_way"
    return "due_today" if target_date == today else "target_date_passed"


def goal_progress(goal: Goal, saved: Decimal, today: date) -> dict:
    """Saved, remaining and percent, plus the weekly and daily amount still needed.

    The per-week and per-day figures are given only while the goal is unreached
    and its target date is still ahead. Weeks are counted as the number of
    weekly deposits left, so a target five days away is one week.
    """
    target = Decimal(goal.target_amount)
    remaining = max(target - saved, Decimal("0"))
    status = _status(goal.target_date, saved >= target, today)
    progress = {
        "saved": float(saved.quantize(CENTS)),
        "remaining": float(remaining.quantize(CENTS)),
        "percent": float((saved / target * 100).quantize(PERCENT_PLACES, rounding=ROUND_HALF_UP)),
        "status": status,
        "days_left": None,
        "weeks_left": None,
        "needed_per_week": None,
        "needed_per_day": None,
    }
    if status != "on_the_way":
        return progress
    days_left = (goal.target_date - today).days
    weeks_left = math.ceil(days_left / 7)
    return {
        **progress,
        "days_left": days_left,
        "weeks_left": weeks_left,
        "needed_per_week": float(_round_up_cents(remaining / weeks_left)),
        "needed_per_day": float(_round_up_cents(remaining / days_left)),
    }
