"""Billing terms stated in plain words, read without AI.

- Intro prices: "charged $2.99/month for 3 months, then $32.99/month starting
  Jan 30, 2027"
- Weekday rules: "First Thursday of each month"
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime

MONEY = r"\$\s?(\d[\d,]*\.?\d{0,2})"

INTRO = re.compile(
    r"(?i)" + MONEY + r"\s*(?:/|per|a)\s*month\s+for\s+(\d{1,2})\s+months?,?\s+then\s+"
    + MONEY + r"\s*(?:/|per|a)\s*month(?:\s+(?:starting|from)\s+([A-Za-z]{3,9}\.? \d{1,2},? \d{4}|\d{1,2} [A-Za-z]{3,9} \d{4}))?"
)
ORDINALS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "last": -1}
WEEKDAYS = {name.lower(): index for index, name in enumerate(calendar.day_name)}
WEEKDAY_RULE = re.compile(
    r"(?i)\b(first|1st|second|2nd|third|3rd|fourth|4th|last)\s+("
    + "|".join(WEEKDAYS) + r")\s+of\s+(?:each|every|the)\s+month"
)


@dataclass
class Terms:
    intro_amount: float | None = None
    full_amount: float | None = None
    intro_ends_on: date | None = None
    next_due: date | None = None          # from a weekday rule


def _money(text: str) -> float:
    return float(text.replace(",", ""))


def _parse_date(text: str) -> date | None:
    cleaned = text.replace(".", "").replace(",", "")
    for fmt in ("%b %d %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    days = calendar.monthrange(year, month)[1]
    matches = [date(year, month, d) for d in range(1, days + 1) if date(year, month, d).weekday() == weekday]
    return matches[-1] if nth == -1 else matches[nth - 1]


def next_weekday_rule(after: date, weekday: int, nth: int) -> date:
    """The next date matching e.g. "first Thursday of the month", after a date."""
    for offset in range(0, 3):
        month = _add_months(after.replace(day=1), offset)
        candidate = nth_weekday(month.year, month.month, weekday, nth)
        if candidate > after:
            return candidate
    raise ValueError("No matching date found")


def read_terms(text: str, received: date) -> Terms:
    terms = Terms()
    flat = re.sub(r"\s+", " ", text or "")
    intro = INTRO.search(flat)
    if intro:
        terms.intro_amount = _money(intro.group(1))
        terms.full_amount = _money(intro.group(3))
        stated = _parse_date(intro.group(4)) if intro.group(4) else None
        terms.intro_ends_on = stated or _add_months(received, int(intro.group(2)))
    rule = WEEKDAY_RULE.search(flat)
    if rule:
        terms.next_due = next_weekday_rule(
            received, WEEKDAYS[rule.group(2).lower()], ORDINALS[rule.group(1).lower()],
        )
    return terms
