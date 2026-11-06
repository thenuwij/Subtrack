"""Find recurring payments in receipts with plain rules, before any AI call.

Most recurring bills are obvious from the receipts alone: the same sender
charges the same amount at a steady gap. Those are decided here for free.
Anything unclear is left for the AI analyzer, so the rules only need to be
right when they answer, not to answer everything:

- a sender that bills several different products (Apple, Google, Amazon...)
- trials, cancellations, refunds and failed payments, whose dates and meaning
  need the wording read
- amounts that vary, or gaps that don't match a normal billing cycle
"""
from __future__ import annotations

import re
from datetime import datetime
from statistics import median

from app.gmail.scanner import ReceiptCandidate

# Senders that bill many different products or pass payments through for
# someone else. The amount and gap alone can't say what the charge is for.
MULTI_PRODUCT_SENDERS = {
    "apple.com", "email.apple.com", "itunes.com",
    "google.com", "payments-noreply.google.com",
    "amazon.com", "amazon.com.au",
    "microsoft.com", "paypal.com", "paypal.com.au",
    "afterpay.com", "zip.co", "klarna.com",
    "ebay.com", "ebay.com.au", "uber.com", "doordash.com", "menulog.com.au",
    "stripe.com", "square.com", "squareup.com",
}

# Single-product senders, so a clean pattern can be named and filed confidently.
KNOWN_SENDERS: dict[str, tuple[str, str]] = {
    "netflix.com": ("Netflix", "streaming"),
    "spotify.com": ("Spotify", "streaming"),
    "disneyplus.com": ("Disney+", "streaming"),
    "stan.com.au": ("Stan", "streaming"),
    "binge.com.au": ("Binge", "streaming"),
    "kayosports.com.au": ("Kayo Sports", "streaming"),
    "youtube.com": ("YouTube Premium", "streaming"),
    "primevideo.com": ("Prime Video", "streaming"),
    "openai.com": ("ChatGPT", "software"),
    "anthropic.com": ("Claude", "software"),
    "github.com": ("GitHub", "software"),
    "notion.so": ("Notion", "software"),
    "canva.com": ("Canva", "software"),
    "adobe.com": ("Adobe", "software"),
    "dropbox.com": ("Dropbox", "cloud"),
    "telstra.com": ("Telstra", "phone_internet"),
    "telstra.com.au": ("Telstra", "phone_internet"),
    "optus.com.au": ("Optus", "phone_internet"),
    "vodafone.com.au": ("Vodafone", "phone_internet"),
    "amaysim.com.au": ("amaysim", "phone_internet"),
    "aussiebroadband.com.au": ("Aussie Broadband", "phone_internet"),
    "originenergy.com.au": ("Origin Energy", "utilities"),
    "agl.com.au": ("AGL", "utilities"),
    "energyaustralia.com.au": ("EnergyAustralia", "utilities"),
    "anytimefitness.com.au": ("Anytime Fitness", "fitness"),
    "anytimefitness.com": ("Anytime Fitness", "fitness"),
    "fitnessfirst.com.au": ("Fitness First", "fitness"),
}

# Wording that changes what a charge means. Any of it hands the sender to the AI.
NEEDS_READING = re.compile(
    r"(?i)\b(trial|cancel+ed|cancel+ation|refund|failed|declined|unsuccessful|"
    r"past due|overdue|price (change|increase)|will not renew|won't renew)\b"
)

# (unit, count, typical gap in days, allowed drift in days)
CADENCES = [
    ("week", 1, 7, 1),
    ("week", 2, 14, 2),
    ("month", 1, 30.4, 3.5),
    ("month", 3, 91.3, 5),
    ("month", 6, 182.6, 7),
    ("year", 1, 365.2, 7),
]

# Small wobble from rounding or a currency rate.
AMOUNT_TOLERANCE = 0.03


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "payment"


def _charges(emails: list[ReceiptCandidate]) -> list[tuple[datetime, float, str]]:
    """One charge per day: invoice and receipt emails for the same charge collapse."""
    by_day: dict[str, ReceiptCandidate] = {}
    for email in emails:
        if email.amount is None or email.amount <= 0 or not email.currency:
            continue
        current = by_day.get(email.date)
        if current is None or (email.confidence == "high" and current.confidence != "high"):
            by_day[email.date] = email
    charges = []
    for day, email in sorted(by_day.items()):
        try:
            when = datetime.fromisoformat(day[:10])
        except ValueError:
            continue
        charges.append((when, float(email.amount), email.currency.upper()))
    return charges


def _cadence(gaps: list[float]) -> tuple[str, int] | None:
    for unit, count, typical, drift in CADENCES:
        if all(abs(gap - typical) <= drift for gap in gaps):
            return unit, count
    return None


def detect(domain: str, emails: list[ReceiptCandidate]):
    """Return a finding when the receipts alone make it clear, else None."""
    from app.gmail.analyzer import DetectedSubscription

    domain = domain.lower()
    if domain in MULTI_PRODUCT_SENDERS or any(domain.endswith("." + d) for d in MULTI_PRODUCT_SENDERS):
        return None
    if any(NEEDS_READING.search(f"{email.subject} {email.excerpt}") for email in emails):
        return None

    charges = _charges(emails)
    if len(charges) < 2 or len({currency for _, _, currency in charges}) != 1:
        return None
    amounts = [amount for _, amount, _ in charges]
    middle = median(amounts)
    if any(abs(amount - middle) > middle * AMOUNT_TOLERANCE for amount in amounts):
        return None
    gaps = [(b[0] - a[0]).days for a, b in zip(charges, charges[1:], strict=False)]
    cadence = _cadence(gaps)
    if cadence is None:
        return None

    known = KNOWN_SENDERS.get(domain)
    merchant, category = known if known else (emails[-1].merchant or domain, "other")
    strong = len(charges) >= 3
    unit, count = cadence
    last_when, last_amount, currency = charges[-1]
    return DetectedSubscription(
        sender_domain=domain,
        merchant=merchant,
        product_key=_slug(merchant),
        interval_unit=unit,
        interval_count=count,
        cadence_confidence="high" if strong else "medium",
        cadence_evidence=f"{len(charges)} charges of the same amount, {', '.join(str(g) for g in gaps)} days apart",
        amount=last_amount,
        currency=currency,
        cancelled=False,
        category=category,
        confidence="high" if strong else "medium",
        charge_count=len(charges),
        last_successful_charge_at=last_when,
    )
