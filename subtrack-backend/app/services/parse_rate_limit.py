"""One per-user limit shared by every endpoint that sends free text to the model."""

import time
from collections import defaultdict, deque

from fastapi import HTTPException

PARSE_CALLS_PER_MINUTE = 10
parse_calls: dict[str, deque[float]] = defaultdict(deque)


def enforce_parse_rate_limit(user_id: str) -> None:
    """Per-process sliding window; the agent limiter counts chat rows, which parsing never writes."""
    now = time.monotonic()
    calls = parse_calls[user_id]
    while calls and now - calls[0] >= 60:
        calls.popleft()
    if len(calls) >= PARSE_CALLS_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a minute and try again.",
            headers={"Retry-After": "60"},
        )
    calls.append(now)
