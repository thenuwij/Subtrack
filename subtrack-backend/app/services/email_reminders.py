"""Opt-in delivery with frozen payloads and Resend's 24-hour idempotency window."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.middleware.auth import is_demo_user
from app.models import EmailPreference, ReminderDelivery, UserPreference
from app.services.alerts import due_alerts
from app.services.email_text import email_safe_name
from app.services.payday_message import payday_message
from app.services.reminders import list_user_reminders


def _deliver(db, *, key, pref, message, now, send, result):
    """Freeze the payload on first sight, then send it at most once."""
    delivery = db.get(ReminderDelivery, key)
    if delivery is None:
        delivery = ReminderDelivery(
            key=key,
            user_id=pref.user_id,
            created_at=now,
            payload={"from": settings.reminder_email_from, "to": [pref.email], **message},
        )
        db.add(delivery)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            delivery = db.get(ReminderDelivery, key)
    if delivery.sent_at:
        return
    # Never retry outside the provider deduplication window.
    if now - delivery.created_at >= timedelta(hours=23):
        result["expired"] += 1
        return
    try:
        response = send(
            "https://api.resend.com/emails",
            json=delivery.payload,
            headers={"Authorization": f"Bearer {settings.resend_api_key}", "Idempotency-Key": key},
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        result["failed"] += 1
        return
    delivery.sent_at = now
    db.commit()
    result["sent"] += 1


def _send_reminders(db, pref, *, now, send, result):
    zone = db.query(UserPreference).filter_by(user_id=pref.user_id).first()
    local_today = (
        now.replace(tzinfo=ZoneInfo("UTC"))
        .astimezone(ZoneInfo(zone.timezone if zone and zone.timezone else "UTC"))
        .date()
    )
    for reminder in list_user_reminders(db, pref.user_id, now=now):
        if not reminder["target_at"] or reminder["status"] in ("dismissed", "inactive", "paused"):
            continue
        target = datetime.fromisoformat(reminder["target_at"].removesuffix("Z"))
        alert = target - timedelta(days=reminder["days_before"])
        # Only before the payment, with a catch-up window from alert day.
        if not alert.date() <= local_today or now >= target:
            continue
        kind = "trial ends" if reminder["kind"] == "trial_end" else "payment due"
        message = {
            "subject": "A payment reminder from Pocketday",
            "text": (
                f"{email_safe_name(reminder['subscription_name'])}: {kind} on {target.date()}.\n\n"
                f"Review your payment: {settings.frontend_url}/subscriptions\n"
                f"Manage or turn off email reminders: {settings.frontend_url}/account#email-reminders"
            ),
        }
        key = f"reminder/{reminder['id']}/{target.isoformat()}"
        _deliver(db, key=key, pref=pref, message=message, now=now, send=send, result=result)


def send_due(db, *, now=None, send=None):
    now = now or datetime.utcnow()
    send = send or httpx.post
    result = {"sent": 0, "failed": 0, "expired": 0}
    if not settings.resend_api_key or not settings.reminder_email_from:
        return {**result, "configured": False}
    users = (
        db.query(EmailPreference)
        .filter(or_(EmailPreference.enabled.is_(True), EmailPreference.payday_enabled.is_(True)))
        .limit(500)
        .all()
    )
    for pref in users:
        if is_demo_user(pref.user_id):
            continue
        if pref.enabled:
            _send_reminders(db, pref, now=now, send=send, result=result)
        if pref.payday_enabled:
            found = payday_message(db, pref.user_id, now=now)
            if found:
                payday, message = found
                key = f"payday/{pref.user_id}/{payday.isoformat()}"
                _deliver(db, key=key, pref=pref, message=message, now=now, send=send, result=result)
            for key, message in due_alerts(db, pref.user_id, now=now):
                _deliver(db, key=key, pref=pref, message=message, now=now, send=send, result=result)
    return {**result, "configured": True}
