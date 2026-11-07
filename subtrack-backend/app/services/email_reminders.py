"""Opt-in delivery with frozen payloads and Resend's 24-hour idempotency window."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models import EmailPreference, ReminderDelivery, UserPreference
from app.services.reminders import list_user_reminders


def send_due(db, *, now=None, send=None):
    now = now or datetime.utcnow()
    send = send or httpx.post
    result = {"sent": 0, "failed": 0, "expired": 0}
    if not settings.resend_api_key or not settings.reminder_email_from:
        return {**result, "configured": False}
    users = db.query(EmailPreference).filter_by(enabled=True).limit(500).all()
    for pref in users:
        zone = db.query(UserPreference).filter_by(user_id=pref.user_id).first()
        local_today = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(zone.timezone if zone and zone.timezone else "UTC")).date()
        for reminder in list_user_reminders(db, pref.user_id, now=now):
            if not reminder["target_at"] or reminder["status"] in ("dismissed", "inactive", "paused"):
                continue
            target = datetime.fromisoformat(reminder["target_at"].removesuffix("Z"))
            alert = target - timedelta(days=reminder["days_before"])
            # Only before the payment, with a catch-up window from alert day.
            if not alert.date() <= local_today or now >= target:
                continue
            key = f"reminder/{reminder['id']}/{target.isoformat()}"
            delivery = db.get(ReminderDelivery, key)
            if delivery is None:
                delivery = ReminderDelivery(key=key, user_id=pref.user_id, created_at=now, payload={
                    "from": settings.reminder_email_from, "to": [pref.email],
                    "subject": "A payment reminder from Subtrack",
                    "text": f"{reminder['subscription_name']}: {'trial ends' if reminder['kind'] == 'trial_end' else 'payment due'} on {target.date()}.\n\nReview your payment: {settings.frontend_url}/subscriptions\nManage or turn off email reminders: {settings.frontend_url}/account#email-reminders",
                })
                db.add(delivery)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    delivery = db.get(ReminderDelivery, key)
            if delivery.sent_at:
                continue
            # Never retry outside the provider deduplication window.
            if now - delivery.created_at >= timedelta(hours=23):
                result["expired"] += 1
                continue
            try:
                response = send("https://api.resend.com/emails", json=delivery.payload,
                    headers={"Authorization": f"Bearer {settings.resend_api_key}", "Idempotency-Key": key}, timeout=15)
                response.raise_for_status()
            except httpx.HTTPError:
                result["failed"] += 1
                continue
            delivery.sent_at = now
            db.commit()
            result["sent"] += 1
    return {**result, "configured": True}
