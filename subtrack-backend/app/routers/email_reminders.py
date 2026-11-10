"""Email preferences use the authenticated account's signed email claim."""

import secrets

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.middleware.auth import reject_demo_user, verify_token
from app.models import EmailPreference
from app.services.email_reminders import send_due

router = APIRouter(prefix="/email-reminders", tags=["email reminders"])


class EmailOptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Payment reminders and the payday email; leave one out to keep it as is.
    enabled: bool | None = None
    payday: bool | None = None

    @model_validator(mode="after")
    def changes_something(self):
        if self.enabled is None and self.payday is None:
            raise ValueError("Choose which emails to turn on or off.")
        return self


@router.get("")
def get_email_preferences(user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    pref = db.get(EmailPreference, user_id)
    return {
        "enabled": bool(pref and pref.enabled),
        "payday": bool(pref and pref.payday_enabled),
        "email": pref.email if pref else None,
        "configured": bool(settings.resend_api_key and settings.reminder_email_from),
    }


@router.put("")
def set_email_preferences(
    body: EmailOptIn, request: Request, user_id: str = Depends(verify_token), db: Session = Depends(get_db)
):
    reject_demo_user(user_id, "Email reminders")
    pref = db.get(EmailPreference, user_id)
    if body.enabled or body.payday:
        if not settings.resend_api_key or not settings.reminder_email_from:
            raise HTTPException(503, "Email delivery is not configured yet")
        # verify_token has already verified signature, audience, expiry and subject.
        claims = jwt.decode(request.headers["authorization"].split()[1], options={"verify_signature": False})
        email = claims.get("email")
        if not isinstance(email, str) or "@" not in email or any(c in email for c in "\r\n"):
            raise HTTPException(422, "Your account needs an email address")
        if pref is None:
            pref = EmailPreference(user_id=user_id, email=email)
            db.add(pref)
        pref.email = email
    if pref and body.enabled is not None:
        pref.enabled = body.enabled
    if pref and body.payday is not None:
        pref.payday_enabled = body.payday
    db.commit()
    return get_email_preferences(user_id, db)


@router.post("/scheduled-send")
def scheduled_send(x_cron_secret: str = Header(default=""), db: Session = Depends(get_db)):
    if not settings.cron_secret or not secrets.compare_digest(x_cron_secret, settings.cron_secret):
        raise HTTPException(403, "Forbidden")
    return send_due(db)
