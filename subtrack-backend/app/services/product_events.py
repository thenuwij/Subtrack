"""Anonymous usage events and the activation and retention summary built from them."""
from __future__ import annotations

import hashlib
import hmac
import logging
import statistics
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import settings
from app.middleware.auth import is_demo_user
from app.models import ProductEvent, ReminderDelivery

logger = logging.getLogger(__name__)

# Events the browser may report; everything else is recorded by the server.
CLIENT_EVENTS = frozenset({"setup_started", "setup_finished", "first_number_seen", "payday_link_clicked"})
SERVER_EVENTS = frozenset({"home_viewed", "afford_check", "balance_updated", "spend_logged", "income_logged"})
ONCE_PER_USER = frozenset({"setup_started", "setup_finished", "first_number_seen"})
ONCE_PER_DAY = frozenset({"home_viewed"})
# Any of these means the person came back and used Pocketday.
ACTIVE_EVENTS = frozenset({
    "home_viewed", "afford_check", "balance_updated", "spend_logged", "income_logged", "payday_link_clicked",
})
FAST_SETUP = timedelta(minutes=3)
CYCLE = timedelta(days=14)


def actor_for(user_id: str) -> str:
    return hmac.new(settings.supabase_jwt_secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def record(db: Session, user_id: str, name: str, *, now: datetime | None = None) -> None:
    """Store one event; never lets a counting problem break the user's request."""
    if name not in CLIENT_EVENTS | SERVER_EVENTS or is_demo_user(user_id):
        return
    now = now or _utcnow()
    actor = actor_for(user_id)
    try:
        query = db.query(ProductEvent).filter(ProductEvent.actor == actor, ProductEvent.name == name)
        if name in ONCE_PER_USER and query.first():
            return
        if name in ONCE_PER_DAY and query.filter(
            ProductEvent.created_at >= datetime.combine(now.date(), time.min)
        ).first():
            return
        db.add(ProductEvent(actor=actor, name=name, created_at=now))
        db.commit()
    except Exception:  # noqa: BLE001 - counting must never fail the request
        db.rollback()
        logger.warning("Could not record product event %s", name, exc_info=True)


def delete_for_user(db: Session, user_id: str) -> int:
    result = db.execute(delete(ProductEvent).where(ProductEvent.actor == actor_for(user_id)))
    return max(0, result.rowcount or 0)


def _pct(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def product_summary(db: Session, since: datetime, *, now: datetime | None = None) -> dict:
    now = now or _utcnow()
    events = db.query(ProductEvent).filter(ProductEvent.created_at >= since).all()
    counts: dict[str, int] = {}
    for event in events:
        counts[event.name] = counts.get(event.name, 0) + 1

    # Setup timing uses each person's first start and finish, whenever they happened.
    firsts: dict[tuple[str, str], datetime] = {}
    for event in db.query(ProductEvent).filter(ProductEvent.name.in_(("setup_started", "setup_finished"))):
        key = (event.actor, event.name)
        if key not in firsts or event.created_at < firsts[key]:
            firsts[key] = event.created_at
    started = {actor for actor, name in firsts if name == "setup_started" and firsts[(actor, name)] >= since}
    durations = [
        firsts[(actor, "setup_finished")] - firsts[(actor, "setup_started")]
        for actor in started
        if (actor, "setup_finished") in firsts
    ]

    # Second-cycle retention: people who finished setup at least 28 days ago and
    # used Pocketday again between days 14 and 28 after finishing.
    finished_at = {actor: at for (actor, name), at in firsts.items() if name == "setup_finished"}
    cohort = {actor: at for actor, at in finished_at.items() if since <= at <= now - 2 * CYCLE}
    active = db.query(ProductEvent).filter(ProductEvent.name.in_(ACTIVE_EVENTS)).all()
    returned = {
        event.actor for event in active
        if event.actor in cohort and cohort[event.actor] + CYCLE <= event.created_at < cohort[event.actor] + 2 * CYCLE
    }
    active_last_cycle = {event.actor for event in active if event.created_at >= now - CYCLE}

    deliveries = db.query(ReminderDelivery).filter(
        ReminderDelivery.sent_at.isnot(None), ReminderDelivery.sent_at >= since,
    )
    payday_sent = sum(1 for row in deliveries if row.key.startswith("payday/"))
    alerts_sent = sum(1 for row in deliveries if row.key.startswith("alert/"))

    return {
        "setup": {
            "started": len(started),
            "finished": len(durations),
            "completion_rate": _pct(len(durations), len(started)),
            "median_minutes": round(statistics.median(d.total_seconds() for d in durations) / 60, 1) if durations else None,
            "under_3_minutes_rate": _pct(sum(1 for d in durations if d <= FAST_SETUP), len(durations)),
        },
        "first_number_seen": counts.get("first_number_seen", 0),
        "active_last_14_days": len(active_last_cycle),
        "retention": {
            "cohort": len(cohort),
            "returned_in_second_cycle": len(returned),
            "rate": _pct(len(returned), len(cohort)),
        },
        "payday_emails": {
            "sent": payday_sent,
            "links_clicked": counts.get("payday_link_clicked", 0),
            "click_rate": _pct(counts.get("payday_link_clicked", 0), payday_sent),
        },
        "alerts_sent": alerts_sent,
        "events": dict(sorted(counts.items())),
    }
