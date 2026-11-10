"""The payday email: what's spoken for until next payday and what's free.

Every figure comes from the safe-to-spend engine; this module only words it.
"""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import settings
from app.models import SafeToSpendProfile
from app.services.recurrence import occurrences_between
from app.services.safe_to_spend import _local_date, _user_zone, safe_to_spend

SEND_FROM_HOUR = 7
MAX_LISTED_BILLS = 8
SYMBOLS = {"AUD": "A$", "USD": "US$", "GBP": "£", "SGD": "S$", "EUR": "€", "JPY": "¥"}


def money(amount: float, currency: str) -> str:
    places = 0 if currency == "JPY" else 2
    return f"{SYMBOLS.get(currency, currency + ' ')}{amount:,.{places}f}"


def _short_date(value: str) -> str:
    day = date.fromisoformat(value[:10])
    return f"{day:%a} {day.day} {day:%b}"


def is_payday(profile: SafeToSpendProfile, day: date) -> bool:
    midnight = datetime.combine(day, time.min)
    return bool(occurrences_between(
        datetime.combine(profile.pay_anchor_on, time.min),
        profile.pay_interval_unit,
        midnight,
        midnight,
        interval_count=profile.pay_interval_count,
    ))


def payday_message(db: Session, user_id: str, *, now: datetime) -> tuple[date, dict] | None:
    """Return (payday, {"subject", "text"}) when today is payday and it's morning locally."""
    profile = db.get(SafeToSpendProfile, user_id)
    if profile is None:
        return None
    zone: ZoneInfo = _user_zone(db, user_id)
    local_now = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone)
    today = _local_date(now, zone)
    if local_now.hour < SEND_FROM_HOUR or not is_payday(profile, today):
        return None

    position = safe_to_spend(db, user_id, now=now)
    links = (
        f"Add today's balance for an exact number: {settings.frontend_url}/balance\n"
        f"Turn off payday emails: {settings.frontend_url}/account#email-reminders"
    )
    if position.get("safe_to_spend") is None:
        next_payday = _short_date(position["next_payday"]) if position.get("next_payday") else "your next payday"
        return today, {
            "subject": "Payday: check what's free to spend",
            "text": (
                f"It's payday. Enter today's balance to see what's free to spend until {next_payday}.\n\n"
                + "\n".join(position.get("warnings", []))
                + f"\n\n{links}"
            ),
        }

    currency = position["base_currency"]
    next_payday = _short_date(position["next_payday"])
    commitments = position["commitments"]
    lines = [f"It's payday. Here's what's spoken for until {next_payday}.", ""]
    if position["mode"] == "estimate":
        lines.append(f"Usual pay: {money(position['pay_amount'], currency)}")
    else:
        lines.append(f"Balance: {money(position['balance'], currency)}")
    lines.append(f"Bills before next payday: {money(position['committed'], currency)}")
    for item in commitments[:MAX_LISTED_BILLS]:
        prefix = "about " if item["is_estimate"] else ""
        lines.append(f"  - {item['name']}, {_short_date(item['due_at'])}: {prefix}{money(item['amount'], currency)}")
    if len(commitments) > MAX_LISTED_BILLS:
        lines.append(f"  - and {len(commitments) - MAX_LISTED_BILLS} more")
    if position.get("set_aside"):
        parts = ", ".join(f"{item['name']} {money(item['amount'], currency)}" for item in position["set_asides"])
        lines.append(f"Set aside: {money(position['set_aside'], currency)} ({parts})")
    lines.append(f"Buffer: {money(position['buffer'], currency)}")
    lines.append("")
    if position["shortfall"]:
        subject = f"Payday: your bills are {money(position['shortfall'], currency)} more than you have"
        lines.append(f"Your bills are {money(position['shortfall'], currency)} more than this pay covers.")
    else:
        per_day = money(position["per_day"], currency)
        subject = f"Payday: about {per_day} a day until {next_payday}"
        lines.append(f"Free to spend: {money(position['safe_to_spend'], currency)}, about {per_day} a day.")
    lines.append("")
    lines.extend(position["warnings"])
    lines.extend(["", links])
    return today, {"subject": subject, "text": "\n".join(lines)}
