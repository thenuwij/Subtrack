"""Anthropic schemas for user-scoped reads and inert action proposals."""
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.actions import (
    ACTION_MODELS,
    ACTION_TOOL_DEFINITIONS,
    create_action_proposal,
)
from app.agent.finance import (
    commitment_changes,
    duplicate_payments,
    financial_overview,
    list_payments,
    payment_detail,
    reminders_overview,
    review_detections,
    saving_candidates,
    upcoming_charges,
)
from app.agent.goals import (
    GOALS_OFF,
    GOALS_TOOLS,
    budget_status_for_month,
    goals_enabled,
    goals_with_progress,
)
from app.agent.research import ALTERNATIVE_RESEARCH_TOOL, research_alternatives
from app.agent.spending import (
    MAX_LIST_LIMIT,
    SPENDING_OFF,
    SPENDING_TOOLS,
    list_logged_transactions,
    logged_transaction_summary,
    spending_enabled,
)
from app.models import Category, TransactionKind
from app.services.safe_to_spend import can_i_afford, safe_to_spend

CATEGORIES = [item.value for item in Category]
MAX_AFFORD_AMOUNT = 9_999_999_999.99
CENTS = Decimal("0.01")


def _utc_date(value: str, *, end_of_day: bool = False) -> datetime:
    """Interpret assistant date-only tool input using Subtrack's UTC policy."""
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    return datetime.combine(parsed, time.max if end_of_day else time.min)


def _purchase_amount(value: object) -> Decimal:
    """Validate a model-supplied purchase amount the same way the REST endpoint does."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("amount must be a number")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("amount must be a number") from exc
    if not amount.is_finite() or amount <= 0 or amount > Decimal(str(MAX_AFFORD_AMOUNT)):
        raise ValueError("amount must be greater than 0 and within the supported range")
    if amount != amount.quantize(CENTS):
        raise ValueError("amount can have at most 2 decimal places")
    return amount


def _month_category_totals(month: dict) -> dict:
    """Per-category totals for one month, so the model never adds them up itself."""
    totals: dict[str, Decimal] = {}
    unconverted = 0
    for charge in month["charges"]:
        amount = charge.get("charge_amount_in_base")
        if amount is None:
            unconverted += 1
            continue
        category = charge.get("category") or "other"
        totals[category] = totals.get(category, Decimal("0")) + Decimal(str(amount))
    extras = sum(
        (Decimal(str(e["amount_in_base"])) for e in month["extras"] if e["amount_in_base"] is not None),
        Decimal("0"),
    )
    return {
        "category_totals_in_base": [
            {"category": name, "total": float(total.quantize(CENTS))}
            for name, total in sorted(totals.items(), key=lambda item: item[1], reverse=True)
        ],
        "category_totals_unconverted_count": unconverted,
        "extras_total_in_base": float(extras.quantize(CENTS)),
    }


READ_TOOL_DEFINITIONS = [
    {
        "name": "get_financial_overview",
        "description": (
            "Get the user's active tracked recurring-payment total, yearly equivalent, "
            "category breakdown, stated income share, and currency-quality metadata. "
            "This covers recurring commitments only, not all bank spending."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_recurring_payments",
        "description": (
            "List the user's active recurring payments, optionally narrowed to IDs selected "
            "in the UI, a category, or a name search. Use this before comparing payments."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subscription_ids": {
                    "type": "array", "maxItems": 25,
                    "items": {"type": "string", "format": "uuid"},
                },
                "category": {"type": "string", "enum": CATEGORIES},
                "query": {"type": "string", "maxLength": 120},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "sort_by": {"type": "string", "enum": ["monthly_cost", "name", "next_due"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_recurring_payment",
        "description": (
            "Get one active recurring payment by ID. IDs from page context are only hints; "
            "this tool re-checks ownership before returning anything."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"subscription_id": {"type": "string", "format": "uuid"}},
            "required": ["subscription_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_upcoming_charges",
        "description": (
            "Get every projected charge occurrence for tracked recurring payments in either "
            "the next 1-730 days or an inclusive UTC date range. This is a forecast, not "
            "recorded transaction history. A weekly payment can appear many times."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": ["integer", "null"], "minimum": 1, "maximum": 730},
                "start_date": {"type": ["string", "null"], "format": "date"},
                "end_date": {"type": ["string", "null"], "format": "date"},
            },
            "required": ["days", "start_date", "end_date"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_commitment_changes",
        "description": (
            "Get additions, removals, and price changes in tracked monthly recurring "
            "commitments for the current month or a recent rolling period."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["current_month", "last_30_days", "last_90_days"],
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "find_duplicate_payments",
        "description": (
            "Find possible duplicate records in the user's tracked list. Suggestions are "
            "read-only and do not prove duplicate bank charges; the user must confirm."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_review_detections",
        "description": (
            "List pending or dismissed inbox detections, optionally limited to detection IDs "
            "visible on the review page. These are unapproved findings and are excluded from totals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "detection_ids": {
                    "type": "array", "maxItems": 25,
                    "items": {"type": "string", "format": "uuid"},
                },
                "status": {"type": "string", "enum": ["pending", "dismissed"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_saving_candidates",
        "description": (
            "Get an evidence-led shortlist of large or recently increased recurring payments "
            "to review. Never call them unnecessary as fact and never imply cancellation is automatic."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 10}},
            "additionalProperties": False,
        },
    },
    {
        "name": "list_payment_reminders",
        "description": (
            "List the user's in-app renewal, cancellation, and trial reminders. "
            "Use visible reminder IDs from page context when the user refers to reminders on screen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reminder_ids": {
                    "type": "array", "maxItems": 25,
                    "items": {"type": "string", "format": "uuid"},
                },
                "status": {
                    "type": "string",
                    "enum": ["all", "due", "upcoming", "overdue", "dismissed"],
                },
                "horizon_days": {"type": "integer", "minimum": 1, "maximum": 730},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_safe_to_spend",
        "description": (
            "Get how much the user can safely spend until their next payday, from their saved "
            "balance, payday, buffer and tracked payments due before then. Returns the amount, "
            "per-day amount, any shortfall, the commitments counted and warnings. "
            "A status other than ready means no safe amount can be given. "
            "For a specific purchase amount, use check_can_i_afford instead."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "check_can_i_afford",
        "description": (
            "Always use this when the user names a purchase amount. "
            "Check whether a one-off purchase fits within the user's safe-to-spend amount "
            "until payday, what would be left overall and per day afterwards, "
            "and how much short the user would be if it doesn't fit. "
            "The amount is in the user's base currency."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": MAX_AFFORD_AMOUNT,
                },
            },
            "required": ["amount"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_paid_history",
        "description": (
            "Get past payment occurrences: confirmed when a Gmail receipt or the user marked it paid, "
            "expected when nothing was seen, or skipped. Also returns bills with their paid status, "
            "late fees total and amounts above the regular price. Each row has a target used by "
            "propose_mark_payment_paid. Use for 'did X go through', 'what did I pay in October' "
            "and late-fee questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"months": {"type": "integer", "minimum": 1, "maximum": 12}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_ways_to_save",
        "description": (
            "Get the same list the Ways to save page shows: price rises in the last 90 days, "
            "trials and intro prices ending within 30 days, late fees and above-plan totals, "
            "and recurring payments' share of income. Use find_duplicate_payments for duplicates."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_month_costs",
        "description": (
            "Get every charge dated in one calendar month, including already paid ones, plus "
            "one-off extras such as late fees. This is the real cost of that month (a weekly "
            "payment counts 4 or 5 times) and matches the dashboard, with totals per category and "
            "for extras. Defaults to this month."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer", "minimum": 2000, "maximum": 2100},
                "month": {"type": "integer", "minimum": 1, "maximum": 12},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_email_reminder_settings",
        "description": "Get whether email reminders before payments and trial ends are turned on.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_gmail_status",
        "description": (
            "Get whether Gmail is connected, when it was last scanned, whether the daily scan "
            "is on and any scan error."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_transactions",
        "description": (
            "List expenses and income the user logged in Subtrack for one calendar month "
            "(defaults to this month), newest first, optionally by kind or category. "
            "These are what the user recorded, not bank data. Use before logging to spot "
            "an entry that is already there, and to find the ID to edit or remove."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "month": {"type": "string", "pattern": "^\\d{4}-\\d{2}$"},
                "kind": {"type": "string", "enum": [item.value for item in TransactionKind]},
                "category": {"type": "string", "enum": CATEGORIES},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIST_LIMIT},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_transaction_summary",
        "description": (
            "Get logged income, expenses, net and expenses per category for one calendar "
            "month (defaults to this month) in the user's base currency. Quote logged "
            "spending totals only from this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"month": {"type": "string", "pattern": "^\\d{4}-\\d{2}$"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_budget_status",
        "description": (
            "Get every category budget's monthly limit, amount spent (logged expenses plus "
            "tracked payments charged that month) and amount left for one calendar month "
            "(defaults to this month) in the user's base currency, with the budget IDs. "
            "Quote budget figures only from this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"month": {"type": "string", "pattern": "^\\d{4}-\\d{2}$"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "list_goals",
        "description": (
            "List the user's savings goals with their IDs, target, saved, remaining, percent, "
            "status and the amount still needed per week and per day. Archived goals are "
            "left out unless include_archived is true. Quote goal figures only from this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"include_archived": {"type": "boolean"}},
            "additionalProperties": False,
        },
    },
    ALTERNATIVE_RESEARCH_TOOL,
]

TOOL_DEFINITIONS = READ_TOOL_DEFINITIONS + ACTION_TOOL_DEFINITIONS


def run_tool(
    tool_name: str,
    tool_input: dict,
    db: Session,
    user_id: str,
    *,
    thread_id: UUID | None = None,
    assistant_message_id: UUID | None = None,
):
    """Dispatch an allow-listed read or create an inert action proposal."""
    if tool_name in SPENDING_TOOLS and not spending_enabled(db, user_id):
        return SPENDING_OFF
    if tool_name in GOALS_TOOLS and not goals_enabled(db, user_id):
        return GOALS_OFF
    if tool_name in ACTION_MODELS:
        if not thread_id or not assistant_message_id:
            return {"error": "Action proposals require a conversation message"}
        return create_action_proposal(
            tool_name,
            tool_input,
            db,
            user_id,
            thread_id=thread_id,
            assistant_message_id=assistant_message_id,
        )
    if tool_name == "get_financial_overview":
        return financial_overview(db, user_id)
    if tool_name == "list_recurring_payments":
        return list_payments(db, user_id, tool_input)
    if tool_name == "get_recurring_payment":
        return payment_detail(db, user_id, tool_input.get("subscription_id", ""))
    if tool_name == "get_upcoming_charges":
        start_date = tool_input.get("start_date")
        end_date = tool_input.get("end_date")
        if bool(start_date) != bool(end_date):
            return {
                "error": "Both start_date and end_date are required for a custom forecast window."
            }
        try:
            if start_date and end_date:
                return upcoming_charges(
                    db,
                    user_id,
                    start_at=_utc_date(start_date),
                    end_at=_utc_date(end_date, end_of_day=True),
                )
            return upcoming_charges(db, user_id, tool_input.get("days") or 30)
        except (TypeError, ValueError) as exc:
            return {"error": str(exc)}
    if tool_name == "get_commitment_changes":
        return commitment_changes(db, user_id, tool_input.get("period", "current_month"))
    if tool_name == "find_duplicate_payments":
        return duplicate_payments(db, user_id)
    if tool_name == "list_review_detections":
        return review_detections(db, user_id, tool_input)
    if tool_name == "get_saving_candidates":
        return saving_candidates(db, user_id, tool_input.get("limit", 5))
    if tool_name == "list_payment_reminders":
        return reminders_overview(db, user_id, tool_input)
    if tool_name == "get_safe_to_spend":
        return safe_to_spend(db, user_id)
    if tool_name == "check_can_i_afford":
        try:
            amount = _purchase_amount(tool_input.get("amount"))
        except ValueError as exc:
            return {"error": str(exc)}
        return can_i_afford(db, user_id, amount)
    if tool_name == "get_paid_history":
        from app.services.paid_history import paid_history
        months = tool_input.get("months", 3)
        if isinstance(months, bool) or not isinstance(months, int) or not 1 <= months <= 12:
            return {"error": "months must be a whole number from 1 to 12"}
        return paid_history(db, user_id, months=months)
    if tool_name == "get_ways_to_save":
        from app.routers.subscriptions import ways_to_save
        return ways_to_save(user_id=user_id, db=db)
    if tool_name == "get_month_costs":
        from app.routers.subscriptions import get_calendar_month
        for key, low, high in (("year", 2000, 2100), ("month", 1, 12)):
            value = tool_input.get(key)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high
            ):
                return {"error": f"{key} must be a whole number from {low} to {high}"}
        result = get_calendar_month(
            year=tool_input.get("year"), month=tool_input.get("month"), user_id=user_id, db=db,
        )
        return {**result, **_month_category_totals(result)}
    if tool_name == "get_email_reminder_settings":
        from app.routers.email_reminders import get_email_preferences
        return get_email_preferences(user_id, db)
    if tool_name == "get_gmail_status":
        from app.routers.gmail import gmail_status
        return gmail_status(user_id=user_id, db=db)
    if tool_name == "list_transactions":
        return list_logged_transactions(db, user_id, tool_input)
    if tool_name == "get_transaction_summary":
        return logged_transaction_summary(db, user_id, tool_input)
    if tool_name == "get_budget_status":
        return budget_status_for_month(db, user_id, tool_input)
    if tool_name == "list_goals":
        return goals_with_progress(db, user_id, tool_input)
    if tool_name == "research_cheaper_alternatives":
        return research_alternatives(db, user_id, tool_input)
    return {"error": "Unknown assistant tool"}
