"""Connect an email finding to a payment the user already tracks, without AI.

Two free signals:

- The names overlap: "Anytime Fitness membership" contains "Anytime Fitness".
  This is only a suggestion; the user confirms it in review.
- The user already said so: a saved sender link for this sender *and* business
  name. Billing platforms (Debitsuccess, Ezidebit...) send receipts for many
  businesses, so the sender alone is never enough.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import SenderLink, Subscription

# Words that describe the bill rather than the business.
FILLER_WORDS = {
    "membership", "subscription", "plan", "payment", "monthly", "weekly", "fortnightly",
    "annual", "yearly", "fee", "fees", "bill", "invoice", "receipt", "direct", "debit",
    "pty", "ltd", "the", "au", "australia",
}


def name_words(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+", (text or "").lower()))
    return words - FILLER_WORDS


def merchant_key(text: str) -> str:
    """Stable key for a business name: its meaningful words, sorted."""
    return "-".join(sorted(name_words(text)))


def name_match(merchant: str, subscriptions: list[Subscription]) -> Subscription | None:
    """The one tracked payment whose name is contained in this finding's name, or vice versa."""
    found = name_words(merchant)
    if not found:
        return None
    matches = []
    for sub in subscriptions:
        tracked = name_words(sub.name)
        if tracked and (tracked <= found or found <= tracked):
            matches.append(sub)
    return matches[0] if len(matches) == 1 else None


def linked_subscription_id(
    links: dict[tuple[str, str], object], sender_domain: str, merchant: str,
):
    return links.get(((sender_domain or "").lower(), merchant_key(merchant)))


def load_links(db: Session, user_id: str) -> dict[tuple[str, str], object]:
    rows = db.query(SenderLink).filter(SenderLink.user_id == user_id).all()
    return {(row.sender_domain, row.merchant_key): row.subscription_id for row in rows}


def remember_link(db: Session, user_id: str, sender_domain: str, merchant: str, subscription_id) -> None:
    domain, key = (sender_domain or "").lower(), merchant_key(merchant)
    if not domain or not key:
        return
    row = db.query(SenderLink).filter(
        SenderLink.user_id == user_id,
        SenderLink.sender_domain == domain,
        SenderLink.merchant_key == key,
    ).first()
    if row is None:
        db.add(SenderLink(user_id=user_id, sender_domain=domain, merchant_key=key,
                          subscription_id=subscription_id))
    else:
        row.subscription_id = subscription_id
