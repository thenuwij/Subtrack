from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.agent.finance import CurrencyContext, upcoming_charges
from app.models import SafeToSpendProfile, UserPreference
from app.services.recurrence import occurrences_between, project_next_occurrence, rewind_anchor
from app.services.set_asides import set_aside_position

CENTS = Decimal("0.01")
BALANCE_STALE_AFTER_DAYS = 3
SCOPE_NOTE = (
    "Covers your entered balance, tracked payments and buffer. Untracked bills "
    "and one-off costs are not included. Payments due on your balance date or "
    "on payday count as still to pay."
)
SCOPE_NOTE_AFTER_PAY = (
    "Covers your entered balance, tracked payments and buffer. Untracked bills "
    "and one-off costs are not included. Payments due on your balance date count "
    "as still to pay; payments due on payday are left for your next pay."
)
ESTIMATE_SCOPE_NOTE = (
    "Estimated from your usual pay, tracked payments and buffer for this pay "
    "cycle. Spending so far, untracked bills and one-off costs are not included."
)
SET_ASIDE_NOTE = (
    " Money you set aside comes off each pay cycle in full; spending you log "
    "from a pot uses up that pot first."
)
ESTIMATE_WARNING = (
    "This is an estimate from your usual pay. Add today's balance for an exact number."
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


def _previous_payday(profile: SafeToSpendProfile, next_payday: date, today: date) -> date:
    return rewind_anchor(
        _midnight(next_payday), profile.pay_interval_unit, _midnight(today), profile.pay_interval_count,
    ).date()


def _bills_end(profile: SafeToSpendProfile, next_payday: date) -> datetime:
    """Bills due on payday belong to this period unless pay lands before them."""
    if profile.payday_bills_after_pay:
        return _midnight(next_payday) - timedelta(microseconds=1)
    return datetime.combine(next_payday, time.max)


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
    """What's free until payday, from today's balance or, without one, from usual pay.

    ``mode`` is "balance" when a balance entered since the last payday is used,
    and "estimate" when the number comes from the usual pay amount instead.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    profile = db.get(SafeToSpendProfile, user_id)
    if profile is None:
        return {"status": "needs_setup", "safe_to_spend": None, "scope": SCOPE_NOTE}

    zone = _user_zone(db, user_id)
    today = _local_date(now, zone)
    next_payday = _next_payday(profile, today)
    balance_day = (
        _local_date(profile.balance_as_of, zone)
        if profile.balance is not None and profile.balance_as_of is not None
        else None
    )
    balance_current = balance_day is not None and not _payday_since_balance(profile, balance_day, today)
    mode = "balance" if balance_current else "estimate"
    result = {
        "status": "ready",
        "mode": mode,
        "safe_to_spend": None,
        "per_day": None,
        "shortfall": None,
        "next_payday": next_payday.isoformat(),
        "days_until_payday": (next_payday - today).days,
        "balance_date": balance_day.isoformat() if balance_day else None,
        "pay_cycle_start": None,
        "profile": {
            "balance": float(profile.balance) if profile.balance is not None else None,
            "pay_amount": float(profile.pay_amount) if profile.pay_amount is not None else None,
            "currency": profile.currency,
            "pay_interval_unit": profile.pay_interval_unit,
            "pay_interval_count": profile.pay_interval_count,
            "buffer": float(profile.buffer),
            "payday_bills_after_pay": bool(profile.payday_bills_after_pay),
        },
        "warnings": [],
        "scope": SCOPE_NOTE_AFTER_PAY if profile.payday_bills_after_pay else SCOPE_NOTE,
    }

    cycle_start = _previous_payday(profile, next_payday, today)
    result["pay_cycle_start"] = cycle_start.isoformat()
    if mode == "estimate":
        if profile.pay_amount is None:
            result["status"] = "balance_outdated"
            result["warnings"].append("A payday has passed since this balance. Update your balance.")
            return result
        # Bills on the last payday came out of the previous pay unless pay lands first.
        start_day = cycle_start if profile.payday_bills_after_pay else cycle_start + timedelta(days=1)
        starting_amount = profile.pay_amount
        window_start = _midnight(start_day)
        spread_days = (next_payday - cycle_start).days
        result["scope"] = ESTIMATE_SCOPE_NOTE
        result["warnings"].append(ESTIMATE_WARNING)
    else:
        starting_amount = profile.balance
        window_start = _midnight(balance_day)
        spread_days = result["days_until_payday"]

    forecast = upcoming_charges(
        db,
        user_id,
        now=now,
        start_at=window_start,
        end_at=_bills_end(profile, next_payday),
        include_past=mode == "estimate",
    )
    currency = CurrencyContext.for_user(db, user_id)
    start_converted, start_quality = currency.convert(float(starting_amount), profile.currency)
    buffer, _ = currency.convert(float(profile.buffer), profile.currency)
    result["base_currency"] = currency.base
    set_asides = set_aside_position(
        db,
        user_id,
        base=currency.base,
        cycle_start=cycle_start,
        cycle_end=next_payday,
        balance_as_of=profile.balance_as_of if mode == "balance" else None,
    )
    if (
        start_converted is None
        or buffer is None
        or forecast["unconverted_occurrence_count"]
        or set_asides is None
    ):
        result["status"] = "incomplete"
        result["warnings"].append(
            "Some amounts could not be converted, so a safe amount can't be worked out right now."
        )
        return result

    charges = forecast["charges"]
    committed = sum((_to_decimal(row["charge_amount_in_base"]) for row in charges), Decimal("0"))
    start_amount = _to_decimal(start_converted)
    buffer_amount = _to_decimal(buffer)
    reserved = set_asides["reserved"].quantize(CENTS)
    spent = set_asides["spent"].quantize(CENTS)
    remaining = start_amount - committed - buffer_amount - reserved - spent
    if set_asides["set_asides"]:
        result["scope"] += SET_ASIDE_NOTE
    safe_amount = max(remaining, Decimal("0"))
    per_day = (safe_amount / spread_days).quantize(CENTS, rounding=ROUND_DOWN)

    if mode == "balance" and (today - balance_day).days >= BALANCE_STALE_AFTER_DAYS:
        result["warnings"].append(
            "This balance is a few days old, and spending since then isn't counted."
        )
    if start_quality == "stale_current_rate" or forecast["currency_conversion"]["rates_stale"]:
        result["warnings"].append("Some amounts use older exchange rates.")
    if forecast["missing_due_date_count"]:
        result["warnings"].append(
            f"{forecast['missing_due_date_count']} tracked payments have no due date and aren't counted."
        )
    if any(row["charge_amount_is_estimate"] for row in charges):
        result["warnings"].append("Some payments are estimates.")

    result.update(
        safe_to_spend=float(safe_amount),
        # Balance mode spreads over the days left; an estimate spreads the whole
        # pay cycle, because spending so far this cycle is unknown.
        per_day=float(per_day),
        per_day_days=spread_days,
        shortfall=float(max(-remaining, Decimal("0"))),
        balance=float(start_amount) if mode == "balance" else None,
        pay_amount=float(start_amount) if mode == "estimate" else None,
        buffer=float(buffer_amount),
        committed=float(committed),
        set_aside=float(reserved),
        spent=float(spent),
        set_asides=set_asides["set_asides"],
        spends=set_asides["spends"],
        commitments=[
            {
                "id": row["id"],
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
    answer = {
        **position, "amount": float(amount), "affordable": None, "left_after": None, "short_by": None,
    }
    if position["safe_to_spend"] is None:
        return answer
    left = _to_decimal(position["safe_to_spend"]) - amount
    answer["affordable"] = left >= 0
    answer["left_after"] = float(max(left, Decimal("0")))
    answer["short_by"] = float(max(-left, Decimal("0")))
    answer["per_day_after"] = float(
        (max(left, Decimal("0")) / position["per_day_days"]).quantize(CENTS, rounding=ROUND_DOWN)
    )
    return answer
