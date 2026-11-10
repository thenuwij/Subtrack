"""Rare, high-value emails between paydays, sent with the payday email opt-in.

Only two things are worth interrupting someone for:
- bills before payday won't fit in what they have;
- a free trial or intro offer ends within three days.

At most two alerts go out per pay cycle. The payday email already covers a
shortfall on payday itself, so that alert waits until the next morning.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import settings
from app.models import ReminderDelivery, SafeToSpendProfile, Subscription
from app.services.email_text import email_safe_name
from app.services.payday_message import SEND_FROM_HOUR, _short_date, is_payday, money
from app.services.recurrence import effective_status
from app.services.safe_to_spend import _local_date, _user_zone, safe_to_spend

MAX_ALERTS_PER_CYCLE = 2
TRIAL_ALERT_DAYS = 3


def _footer() -> str:
    return (
        f"Open Pocketday: {settings.frontend_url}/dashboard\n"
        f"Turn off payday emails and alerts: {settings.frontend_url}/account#email-reminders"
    )


def due_alerts(db: Session, user_id: str, *, now: datetime) -> list[tuple[str, dict]]:
    """Return (delivery key, {"subject", "text"}) pairs to send now, within the cycle cap."""
    profile = db.get(SafeToSpendProfile, user_id)
    if profile is None:
        return []
    zone: ZoneInfo = _user_zone(db, user_id)
    if now.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone).hour < SEND_FROM_HOUR:
        return []
    today = _local_date(now, zone)
    position = safe_to_spend(db, user_id, now=now)
    if not position.get("pay_cycle_start"):
        return []
    cycle_start = position["pay_cycle_start"]
    currency = position.get("base_currency") or profile.currency

    candidates: list[tuple[str, dict]] = []
    if position.get("shortfall") and not is_payday(profile, today):
        payday = _short_date(position["next_payday"])
        candidates.append((
            f"alert/shortfall/{user_id}/{cycle_start}",
            {
                "subject": f"Heads up: bills before {payday} are {money(position['shortfall'], currency)} more than you have",
                "text": (
                    f"Your bills and set-asides before {payday} add up to "
                    f"{money(position['shortfall'], currency)} more than you have.\n\n"
                    + "\n".join(position.get("warnings", []))
                    + f"\n\n{_footer()}"
                ),
            },
        ))

    trial_window_end = today + timedelta(days=TRIAL_ALERT_DAYS)
    trials = (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id, Subscription.trial_ends_at.isnot(None))
        .order_by(Subscription.trial_ends_at, Subscription.id)
        .all()
    )
    for sub in trials:
        ends_on = _local_date(sub.trial_ends_at, zone)
        if not today <= ends_on <= trial_window_end or effective_status(sub, now) != "active":
            continue
        after = money(sub.amount, sub.currency)
        name = email_safe_name(sub.name)
        candidates.append((
            f"alert/trial/{sub.id}/{ends_on.isoformat()}",
            {
                "subject": f"{name}: offer ends {_short_date(ends_on.isoformat())}",
                "text": (
                    f"The free trial or intro price for {name} ends on {_short_date(ends_on.isoformat())}. "
                    f"After that it's {after} each time it charges.\n\n{_footer()}"
                ),
            },
        ))

    if not candidates:
        return []
    cycle_start_at = datetime.combine(datetime.fromisoformat(cycle_start).date(), time.min)
    sent_this_cycle = (
        db.query(ReminderDelivery)
        .filter(
            ReminderDelivery.user_id == user_id,
            ReminderDelivery.key.like("alert/%"),
            ReminderDelivery.created_at >= cycle_start_at,
        )
        .count()
    )
    room = max(MAX_ALERTS_PER_CYCLE - sent_this_cycle, 0)
    existing = [(key, msg) for key, msg in candidates if db.get(ReminderDelivery, key) is not None]
    new = [(key, msg) for key, msg in candidates if db.get(ReminderDelivery, key) is None]
    # Already-created alerts are retried by the delivery code; new ones must fit the cap.
    return existing + new[:room]
