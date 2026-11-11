"""Turn a forwarded email (raw RFC 822 bytes) into a receipt candidate.

Shares the scanner's parsing so forwarded mail and Gmail scans read bills the
same way. Like the scanner, only derived fields leave this module: the raw
message and its full body are never returned or stored.
"""
import hashlib
import re
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from typing import NamedTuple

from app.gmail.redaction import redact
from app.gmail.scanner import (
    ReceiptCandidate,
    _bill_fields,
    _excerpt,
    _merchant_from_sender,
    _parse_amount,
    _term_fields,
    html_to_text,
    pick_body_text,
)

GMAIL_CONFIRMATION_SENDER = "forwarding-noreply@google.com"
_CONFIRMATION_SUBJECT = re.compile(
    r"(?:\(#(\d{4,16})\)\s*)?Gmail Forwarding Confirmation\s*-\s*Receive Mail from\s+<?([\w.+-]+@[\w.-]+)>?",
    re.IGNORECASE,
)
_CONFIRMATION_LINK = re.compile(r"https://mail\.google\.com/mail/vf-[^\s<>\"')]+")


class ForwardingConfirmation(NamedTuple):
    gmail_address: str
    code: str | None
    link: str | None


# One-time codes, account security and health mail never enter the pipeline.
_SENSITIVE = re.compile(
    r"(?i)\b(one[- ]time (pass(code|word)|code|pin)|otp|passcode|"
    r"(verification|security|login|sign[- ]in|authentication) code|"
    r"verify your (email|account|identity)|two[- ]factor|2fa|"
    r"(reset|change) your password|password (reset|change|recovery)|"
    r"new (sign[- ]in|login|device)|sign[- ]in (alert|attempt)|login (alert|attempt)|"
    r"security (alert|notice|warning)|suspicious (activity|sign[- ]in|login)|"
    r"pathology|lab results?|test results?|prescriptions?|diagnos(is|es|ed)|"
    r"medical (record|report|certificate)s?|patient|telehealth|medical referral)\b"
)

# Cloudflare Email Routing adds its own result header on top of the message.
_TRUSTED_AUTHSERV_ID = "mx.cloudflare.net"


def parse_message(raw: bytes) -> EmailMessage:
    return BytesParser(policy=policy.default).parsebytes(raw)


def message_hash(user_id: str, message: EmailMessage, raw: bytes) -> str:
    """Stable per-user id: the Message-ID header, or the bytes when it is missing."""
    message_id = str(message.get("Message-ID", "")).strip()
    source = message_id.encode() if message_id else raw
    return hashlib.sha256(user_id.encode() + b"\0" + source).hexdigest()


def header(message: EmailMessage, name: str) -> str:
    return re.sub(r"\s+", " ", str(message.get(name, ""))).strip()


def sender_address(message: EmailMessage) -> str:
    return parseaddr(header(message, "From"))[1].lower()


def body_text(message: EmailMessage) -> str:
    by_type: dict[str, list[str]] = {}
    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in ("text/plain", "text/html"):
            continue
        try:
            text = part.get_content()
        except (LookupError, ValueError):
            text = (part.get_payload(decode=True) or b"").decode("utf-8", errors="ignore")
        if content_type == "text/html":
            text = html_to_text(text)
        if text.strip():
            by_type.setdefault(content_type, []).append(text)
    return pick_body_text(by_type)


def is_sensitive(subject: str, body: str) -> bool:
    return bool(_SENSITIVE.search(subject) or _SENSITIVE.search(body))


def forwarding_confirmation(message: EmailMessage) -> ForwardingConfirmation | None:
    """Gmail's forwarding confirmation: the Gmail address plus a code or confirm link.

    Older confirmations put the code in the subject; newer ones only carry a
    link in the body.
    """
    if sender_address(message) != GMAIL_CONFIRMATION_SENDER:
        return None
    match = _CONFIRMATION_SUBJECT.search(header(message, "Subject"))
    if not match:
        return None
    link = _CONFIRMATION_LINK.search(body_text(message))
    if match.group(1) is None and link is None:
        return None
    return ForwardingConfirmation(match.group(2).lower(), match.group(1), link.group(0) if link else None)


def passes_authentication(message: EmailMessage, domains: set[str]) -> bool:
    """Cloudflare saw SPF pass for an envelope sender at one of ``domains``.

    Only the topmost Authentication-Results header counts, and only when it is
    Cloudflare's: anything below it came with the message and can be forged.
    DKIM is not enough: a DKIM-signed Gmail message can be replayed from any
    server, while SPF proves Google itself delivered this copy.
    """
    results = message.get_all("Authentication-Results") or []
    if not results:
        return False
    value = re.sub(r"\([^)]*\)", " ", re.sub(r"\s+", " ", str(results[0])))
    authserv_id, _, rest = value.partition(";")
    if authserv_id.strip().split(" ")[0].lower() != _TRUSTED_AUTHSERV_ID:
        return False
    for result in rest.split(";"):
        if not re.match(r"\s*spf\s*=\s*pass\b", result, re.IGNORECASE):
            continue
        found = re.search(r"smtp\.mailfrom\s*=\s*(\S+)", result, re.IGNORECASE)
        if found and found.group(1).rsplit("@", 1)[-1].lower() in domains:
            return True
    return False


def _received_at(message: EmailMessage) -> datetime:
    try:
        received = parsedate_to_datetime(header(message, "Date"))
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
    if received.tzinfo is None:
        return received.replace(tzinfo=timezone.utc)
    return received.astimezone(timezone.utc)


def to_candidate(message: EmailMessage, message_id: str, body: str) -> ReceiptCandidate:
    merchant, domain = _merchant_from_sender(header(message, "From"))
    subject = header(message, "Subject")
    amount, currency, confidence = _parse_amount(f"{subject}\n{body}")
    received = _received_at(message)
    return ReceiptCandidate(
        message_id=message_id,
        sender_domain=domain,
        merchant=merchant,
        subject=redact(subject)[:120],
        date=received.strftime("%Y-%m-%d"),
        amount=amount,
        currency=currency,
        confidence=confidence,
        excerpt=_excerpt(body),
        **_bill_fields(subject, body),
        **_term_fields(f"{subject}\n{body}", received.date()),
    )
