from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.agent.finance import CurrencyContext, upcoming_charges
from app.models import SafeToSpendProfile, UserPreference
from app.services.recurrence import occurrences_between, project_next_occurrence

CENTS = Decimal("0.01")
BALANCE_STALE_AFTER_DAYS = 3
SCOPE_NOTE = (
    "Covers your entered balance, tracked payments and buffer. Untracked bills "
    "and one-off costs are not included. Payments due on your balance date or "
    "on payday count as still to pay."
)


def _user_zone(db: Session, user_id: str) -> ZoneInfo:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    try:
        return ZoneInfo(pref.timezone if pref and pref.timezone else "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _local_date(value_utc: datetime, zone: ZoneInfo) -> date:
    return value_utc.replace(tzinfo=timezone.utc).astimezone(zone).date()


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min)


def _next_payday(profile: SafeToSpendProfile, today: date) -> date:
    due, _ = project_next_occurrence(
        _midnight(profile.pay_anchor_on),
        profile.pay_interval_unit,
        _midnight(today + timedelta(days=1)),
        profile.pay_interval_count,
    )
    return due.date()


def _payday_since_balance(profile: SafeToSpendProfile, balance_day: date, today: date) -> bool:
    if today <= balance_day:
        return False
    return bool(
        occurrences_between(
            _midnight(profile.pay_anchor_on),
            profile.pay_interval_unit,
            _midnight(balance_day + timedelta(days=1)),
            _midnight(today),
            interval_count=profile.pay_interval_count,
        )
    )


def _to_decimal(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(CENTS)


def safe_to_spend(db: Session, user_id: str, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    profile = db.get(SafeToSpendProfile, user_id)
    if profile is None:
        return {"status": "needs_setup", "safe_to_spend": None, "scope": SCOPE_NOTE}

    zone = _user_zone(db, user_id)
    today = _local_date(now, zone)
    balance_day = _local_date(profile.balance_as_of, zone)
    next_payday = _next_payday(profile, today)
    days_until_payday = (next_payday - today).days
    result = {
        "status": "ready",
        "safe_to_spend": None,
        "per_day": None,
        "shortfall": None,
        "next_payday": next_payday.isoformat(),
        "days_until_payday": days_until_payday,
        "balance_date": balance_day.isoformat(),
        "profile": {
            "balance": float(profile.balance),
            "currency": profile.currency,
            "pay_interval_unit": profile.pay_interval_unit,
            "pay_interval_count": profile.pay_interval_count,
            "buffer": float(profile.buffer),
        },
        "warnings": [],
        "scope": SCOPE_NOTE,
    }
    if _payday_since_balance(profile, balance_day, today):
        result["status"] = "balance_outdated"
        result["warnings"].append("A payday has passed since this balance. Update your balance.")
        return result

    forecast = upcoming_charges(
        db,
        user_id,
        now=now,
        start_at=_midnight(balance_day),
        end_at=datetime.combine(next_payday, time.max),
    )
    currency = CurrencyContext.for_user(db, user_id)
    balance, balance_quality = currency.convert(float(profile.balance), profile.currency)
    buffer, _ = currency.convert(float(profile.buffer), profile.currency)
    result["base_currency"] = currency.base
    if balance is None or buffer is None or forecast["unconverted_occurrence_count"]:
        result["status"] = "incomplete"
        result["warnings"].append(
            "Some amounts could not be converted, so a safe amount can't be worked out right now."
        )
        return result

    charges = forecast["charges"]
    committed = sum((_to_decimal(row["charge_amount_in_base"]) for row in charges), Decimal("0"))
    balance_amount = _to_decimal(balance)
    buffer_amount = _to_decimal(buffer)
    remaining = balance_amount - committed - buffer_amount
    safe_amount = max(remaining, Decimal("0"))
    per_day = (safe_amount / days_until_payday).quantize(CENTS, rounding=ROUND_DOWN)

    if (today - balance_day).days >= BALANCE_STALE_AFTER_DAYS:
        result["warnings"].append(
            "This balance is a few days old, and spending since then isn't counted."
        )
    if balance_quality == "stale_current_rate" or forecast["currency_conversion"]["rates_stale"]:
        result["warnings"].append("Some amounts use older exchange rates.")
    if forecast["missing_due_date_count"]:
        result["warnings"].append(
            f"{forecast['missing_due_date_count']} tracked payments have no due date and aren't counted."
        )
    if any(row["charge_amount_is_estimate"] for row in charges):
        result["warnings"].append("Some payments are estimates.")

    result.update(
        safe_to_spend=float(safe_amount),
        per_day=float(per_day),
        shortfall=float(max(-remaining, Decimal("0"))),
        balance=float(balance_amount),
        buffer=float(buffer_amount),
        committed=float(committed),
        commitments=[
            {
                "name": row["name"],
                "due_at": row["due_at"],
                "amount": row["charge_amount_in_base"],
                "is_estimate": row["charge_amount_is_estimate"],
            }
            for row in charges
        ],
    )
    return result


def can_i_afford(db: Session, user_id: str, amount: Decimal, *, now: datetime | None = None) -> dict:
    position = safe_to_spend(db, user_id, now=now)
    answer = {**position, "amount": float(amount), "affordable": None, "left_after": None}
    if position["safe_to_spend"] is None:
        return answer
    left = _to_decimal(position["safe_to_spend"]) - amount
    answer["affordable"] = left >= 0
    answer["left_after"] = float(max(left, Decimal("0")))
    answer["per_day_after"] = float(
        (max(left, Decimal("0")) / position["days_until_payday"]).quantize(CENTS, rounding=ROUND_DOWN)
    )
    return answer
