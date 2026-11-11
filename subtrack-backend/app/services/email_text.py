"""Plain-text helpers for user-chosen words that go into outgoing email."""

import re

_URL = re.compile(r"(?:[a-z][a-z0-9+.-]*://|www\.)\S*", re.IGNORECASE)
_DOMAIN = re.compile(r"\b(?:[\w-]+\.)+[a-z]{2,}\b", re.IGNORECASE)
MAX_NAME_LENGTH = 60


def email_safe_name(name: str) -> str:
    """Return a payment name that mail clients won't turn into a link.

    Names are typed by the account holder, and the email is sent from
    Subtrack's domain, so links and domains are removed or broken apart.
    """
    text = _URL.sub("", name)
    text = _DOMAIN.sub(lambda match: match.group(0).replace(".", " "), text)
    text = " ".join("".join(char if char.isprintable() else " " for char in text).split())
    return text[:MAX_NAME_LENGTH].strip() or "A payment"
