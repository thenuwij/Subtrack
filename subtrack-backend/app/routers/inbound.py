"""Forwarded email from the Cloudflare Email Worker.

Each user forwards their Gmail to a private ``<token>@<inbound domain>``
address. The Worker signs every delivery; this endpoint checks the signature,
checks the mail really came from the user's confirmed Gmail, drops sensitive
email, and feeds the rest into the same bill pipeline as a Gmail scan. No email
text is stored: only derived receipt fields and a hashed message id.
"""
import base64
import binascii
import hashlib
import hmac
import logging
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import quoteattr

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.gmail import mime
from app.gmail.scanner import ReceiptCandidate
from app.middleware.auth import verify_token
from app.models import DetectedSubscription, InboundAddress, InboundMessage, Subscription

# The scan pipeline still lives in the Gmail router; it moves to a service once
# Gmail OAuth is retired.
from app.routers.gmail import (
    _apply_detections,
    _apply_stated_terms,
    _save_bills,
    _save_receipts,
    _terms_by_domain,
    remove_duplicate_findings,
)
from app.services.payment_links import load_links

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/inbound", tags=["inbound"])

MAX_RAW_BYTES = 8 * 1024 * 1024
# Base64 grows the message by a third; the JSON envelope adds a little more.
MAX_BODY_BYTES = MAX_RAW_BYTES * 4 // 3 + 64 * 1024
MAX_CLOCK_SKEW_SECONDS = 300
GMAIL_DOMAINS = {"gmail.com", "google.com"}
GOOGLE_DOMAINS = {"google.com"}
TOKEN_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
TOKEN_LENGTH = 20
CODE_VISIBLE_FOR = timedelta(hours=24)
# What the Gmail filter forwards: bills and receipts, never sign-in or security mail.
BILL_SEARCH = (
    'subject:(receipt OR invoice OR bill OR payment OR subscription OR renewal OR statement '
    'OR "tax invoice" OR "free trial") '
    '-subject:(code OR password OR verify OR verification OR "sign in" OR security)'
)

# Model calls are network-bound. A small pool of its own keeps a burst of
# forwarded mail from taking the Gmail scanner's slots.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="inbound-email")


class InboundEmail(BaseModel):
    envelope_from: str = Field(max_length=640)
    envelope_to: str = Field(max_length=640)
    raw: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _raw_body(request: Request) -> bytes:
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Email too large")
    return body


def _verify_signature(body: bytes, timestamp: str | None, signature: str | None) -> None:
    try:
        sent_at = int(timestamp or "")
    except ValueError:
        sent_at = None
    if sent_at is None or not signature or abs(time.time() - sent_at) > MAX_CLOCK_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="Not authorised")
    expected = hmac.new(
        settings.inbound_email_secret.encode(),
        f"{sent_at}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature.strip().lower()):
        raise HTTPException(status_code=401, detail="Not authorised")


def _token_for(envelope_to: str) -> str | None:
    local, _, domain = envelope_to.strip().strip("<>").rpartition("@")
    if not local or domain.lower() != settings.inbound_email_domain.lower():
        return None
    return local.lower()


def _forwarded_from(envelope_from: str) -> str:
    """``alice+caf_=...@gmail.com`` (Gmail's forwarding sender) -> ``alice@gmail.com``."""
    local, _, domain = envelope_from.strip().strip("<>").lower().rpartition("@")
    return f"{local.split('+caf_', 1)[0]}@{domain}"


def _outcome(outcome: str, token: str | None, message_id: str | None = None) -> dict:
    logger.info(
        "Inbound email token=%s… hash=%s outcome=%s",
        (token or "")[:4],
        (message_id or "")[:12],
        outcome,
    )
    return {"outcome": outcome}


@router.post("/email", include_in_schema=False)
def receive_email(
    body: bytes = Depends(_raw_body),
    x_inbound_timestamp: str | None = Header(default=None),
    x_inbound_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not settings.inbound_email_secret:
        raise HTTPException(status_code=404, detail="Not Found")
    _verify_signature(body, x_inbound_timestamp, x_inbound_signature)
    try:
        payload = InboundEmail.model_validate_json(body)
        raw = base64.b64decode(payload.raw, validate=True)
    except (ValidationError, binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Malformed email payload") from exc
    if len(raw) > MAX_RAW_BYTES:
        raise HTTPException(status_code=413, detail="Email too large")

    token = _token_for(payload.envelope_to)
    address = (
        db.query(InboundAddress).filter(InboundAddress.token == token).first() if token else None
    )
    # Unknown and paused addresses look the same, so tokens can't be probed.
    if address is None or address.status == "paused":
        return _outcome("rejected", token)

    message = mime.parse_message(raw)
    confirmation = mime.forwarding_confirmation(message)
    if confirmation is not None:
        # Only an address still being set up can learn which Gmail it trusts.
        verified = address.status == "pending" and mime.passes_authentication(message, GOOGLE_DOMAINS)
    else:
        verified = bool(address.gmail_address) and (
            _forwarded_from(payload.envelope_from) == address.gmail_address.lower()
            and mime.passes_authentication(message, GMAIL_DOMAINS)
        )
    if not verified:
        return _outcome("rejected", token)

    message_id = mime.message_hash(address.user_id, message, raw)
    if db.query(InboundMessage.id).filter(
        InboundMessage.user_id == address.user_id,
        InboundMessage.message_hash == message_id,
    ).first():
        return _outcome("duplicate", token, message_id)

    candidate: ReceiptCandidate | None = None
    if confirmation is not None:
        outcome = "confirmation"
        address.confirmation_code, address.gmail_address = confirmation
        address.confirmation_received_at = _utcnow()
    else:
        body_text = mime.body_text(message)
        if mime.is_sensitive(mime.header(message, "Subject"), body_text):
            outcome = "filtered"
        else:
            outcome = "accepted"
            candidate = mime.to_candidate(message, message_id, body_text)
            address.status = "active"
            address.confirmation_code = None
    del message, raw

    user_id, gmail_address = address.user_id, address.gmail_address
    db.add(InboundMessage(user_id=user_id, message_hash=message_id, outcome=outcome))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _outcome("duplicate", token, message_id)

    if candidate is not None:
        _executor.submit(_process_candidate, user_id, candidate, gmail_address)
    return _outcome(outcome, token, message_id)


def _process_candidate(user_id: str, candidate: ReceiptCandidate, gmail_address: str | None) -> None:
    """Save the receipt or bill, then look for a recurring payment, as a scan does."""
    from app.gmail.analyzer import AnalysisFailed, analyze_bounded
    from app.gmail.redaction import redact_owner

    db = SessionLocal()
    try:
        _save_receipts(db, user_id, [candidate])
        _save_bills(db, user_id, [candidate])
        subscriptions = db.query(Subscription).filter(Subscription.user_id == user_id).all()
        existing = db.query(DetectedSubscription).filter(DetectedSubscription.user_id == user_id).all()
        links = load_links(db, user_id)
        terms_by_domain = _terms_by_domain([candidate])

        def apply_batch(found) -> None:
            _apply_stated_terms(found, terms_by_domain)
            _apply_detections(db, user_id, subscriptions, existing, found, links)
            db.commit()

        try:
            analyze_bounded(redact_owner([candidate], gmail_address), on_batch=apply_batch)
        except AnalysisFailed:
            logger.warning("Could not analyse forwarded email hash=%s", candidate.message_id[:12])
            return
        remove_duplicate_findings(db, user_id)
    except Exception:
        db.rollback()
        logger.exception("Could not process forwarded email hash=%s", candidate.message_id[:12])
    finally:
        db.close()


def shutdown_inbound_executor() -> None:
    _executor.shutdown(wait=True, cancel_futures=True)


class PauseRequest(BaseModel):
    paused: bool


def _new_token() -> str:
    return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))


def _get_or_create_address(db: Session, user_id: str) -> InboundAddress:
    address = db.query(InboundAddress).filter(InboundAddress.user_id == user_id).first()
    if address is None:
        address = InboundAddress(user_id=user_id, token=_new_token(), status="pending")
        db.add(address)
        db.commit()
    return address


def _address_text(address: InboundAddress) -> str:
    return f"{address.token}@{settings.inbound_email_domain}"


def _address_view(db: Session, address: InboundAddress) -> dict:
    received_at, count = (
        db.query(func.max(InboundMessage.received_at), func.count(InboundMessage.id))
        .filter(InboundMessage.user_id == address.user_id, InboundMessage.outcome == "accepted")
        .one()
    )
    code_fresh = (
        address.confirmation_received_at is not None
        and _utcnow() - address.confirmation_received_at < CODE_VISIBLE_FOR
    )
    return {
        "address": _address_text(address),
        "status": address.status,
        "gmail_address": address.gmail_address,
        "confirmation_code": address.confirmation_code if address.status == "pending" and code_fresh else None,
        "last_received_at": received_at.isoformat() if received_at else None,
        "received_count": count,
        "filter_query": BILL_SEARCH,
    }


@router.get("/address")
def get_address(user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    return _address_view(db, _get_or_create_address(db, user_id))


@router.post("/address/rotate")
def rotate_address(user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    address = _get_or_create_address(db, user_id)
    address.token = _new_token()
    address.status = "pending"
    address.gmail_address = None
    address.confirmation_code = None
    address.confirmation_received_at = None
    address.rotated_at = _utcnow()
    db.commit()
    return _address_view(db, address)


@router.patch("/address")
def pause_address(
    body: PauseRequest, user_id: str = Depends(verify_token), db: Session = Depends(get_db)
):
    address = _get_or_create_address(db, user_id)
    address.status = "paused" if body.paused else ("active" if address.gmail_address else "pending")
    db.commit()
    return _address_view(db, address)


@router.delete("/address", status_code=204)
def delete_address(user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    db.query(InboundMessage).filter(InboundMessage.user_id == user_id).delete()
    db.query(InboundAddress).filter(InboundAddress.user_id == user_id).delete()
    db.commit()
    return Response(status_code=204)


@router.get("/filter.xml")
def gmail_filter(user_id: str = Depends(verify_token), db: Session = Depends(get_db)):
    address = _get_or_create_address(db, user_id)
    xml = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<feed xmlns='http://www.w3.org/2005/Atom' xmlns:apps='http://schemas.google.com/apps/2006'>"
        "<title>Pocketday bill forwarding</title>"
        "<entry><category term='filter'></category><title>Mail Filter</title>"
        f"<apps:property name='hasTheWord' value={quoteattr(BILL_SEARCH)}/>"
        f"<apps:property name='forwardTo' value={quoteattr(_address_text(address))}/>"
        "</entry></feed>"
    )
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="pocketday-filter.xml"'},
    )
