"""User-scoped assistant reads for logged expenses and income.

Both tools reuse the transaction services behind the REST API, so the assistant
quotes the same rows and totals the Spending page shows.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.agent.finance import CurrencyContext
from app.models import Category, Transaction, TransactionKind
from app.routers.transactions import MONTH_PATTERN, _year_month, transaction_payload
from app.services.features import feature_enabled
from app.services.transactions import amount_in_base, month_summary, month_transactions

SPENDING_FEATURE = "spending"
SPENDING_OFF = {"error": "Expenses and income is turned off in Settings."}
SPENDING_TOOLS = frozenset({
    "list_transactions",
    "get_transaction_summary",
    "propose_log_transaction",
    "propose_update_transaction",
    "propose_remove_transaction",
})
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 100
SCOPE_NOTE = "Entries the user logged in Subtrack, not bank data. They may be incomplete."


def spending_enabled(db: Session, user_id: str) -> bool:
    return feature_enabled(db, user_id, SPENDING_FEATURE)


def _month(db: Session, user_id: str, tool_input: dict) -> tuple[int, int]:
    month = tool_input.get("month")
    if month is not None and (not isinstance(month, str) or not re.fullmatch(MONTH_PATTERN, month)):
        raise ValueError("month must look like 2026-11")
    return _year_month(db, user_id, month)


def _quality(row: Transaction, currency: CurrencyContext, value: object) -> str:
    if value is None:
        return "unconverted"
    if row.currency == currency.base:
        return "exact_base_currency"
    return "stale_current_rate" if currency.snapshot and currency.snapshot.get("stale") else "current_rate"


def list_logged_transactions(db: Session, user_id: str, tool_input: dict) -> dict:
    try:
        year, month = _month(db, user_id, tool_input)
        kind = TransactionKind(tool_input["kind"]) if tool_input.get("kind") else None
        category = Category(tool_input["category"]) if tool_input.get("category") else None
    except ValueError as exc:
        return {"error": str(exc)}
    limit = tool_input.get("limit", DEFAULT_LIST_LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIST_LIMIT:
        return {"error": f"limit must be a whole number from 1 to {MAX_LIST_LIMIT}"}

    currency = CurrencyContext.for_user(db, user_id)
    rows = month_transactions(db, user_id, year, month, kind=kind, category=category, limit=limit + 1)
    returned = rows[:limit]
    entries = []
    qualities = []
    for row in returned:
        value = amount_in_base(row, currency.base, currency.snapshot)
        qualities.append(_quality(row, currency, value))
        entries.append({**transaction_payload(row), "amount_in_base": float(value) if value is not None else None})
    return {
        "scope": SCOPE_NOTE,
        "month": f"{year:04d}-{month:02d}",
        "transactions": entries,
        "returned_count": len(entries),
        "more_available": len(rows) > limit,
        "currency_conversion": currency.metadata(qualities),
    }


def logged_transaction_summary(db: Session, user_id: str, tool_input: dict) -> dict:
    try:
        year, month = _month(db, user_id, tool_input)
    except ValueError as exc:
        return {"error": str(exc)}
    currency = CurrencyContext.for_user(db, user_id)
    qualities = [
        _quality(row, currency, amount_in_base(row, currency.base, currency.snapshot))
        for row in month_transactions(db, user_id, year, month)
    ]
    return {
        "scope": SCOPE_NOTE,
        **month_summary(db, user_id, year, month),
        "currency_conversion": currency.metadata(qualities),
    }
