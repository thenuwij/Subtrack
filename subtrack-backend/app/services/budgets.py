"""What each category budget has spent and has left in one calendar month.

Spending is the user's logged expenses plus their tracked payments charged in
that month. A logged expense linked to a tracked payment that is charged that
month is the same money, so only the payment is counted.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Budget, Category, Transaction, TransactionKind
from app.routers.rates import get_cached_rate_snapshot
from app.services.payment_charges import charged_payment_ids, month_payment_charges
from app.services.transactions import (
    CENTS,
    _snapshot_time,
    amount_in_base,
    base_currency_for,
    month_bounds,
)

NEAR_LIMIT_SHARE = Decimal("0.8")
SHARE_PLACES = Decimal("0.0001")
ZERO = Decimal("0")


def _category_value(category: Category | str) -> str:
    return category.value if isinstance(category, Category) else category


class _CategorySpend:
    def __init__(self) -> None:
        self.logged: dict[str, Decimal] = {}
        self.payments: dict[str, Decimal] = {}
        self.unconverted: Counter[str] = Counter()

    def add(self, bucket: dict[str, Decimal], category: str, amount: Decimal | None) -> None:
        if amount is None:
            self.unconverted[category] += 1
            return
        bucket[category] = bucket.get(category, ZERO) + amount


def _add_tracked_payments(db: Session, user_id: str, year: int, month: int, spend: _CategorySpend) -> set[str]:
    """Add the month's tracked charges and extras; return the IDs of payments charged."""
    charges = month_payment_charges(db, user_id, year, month)
    for charge in charges:
        spend.add(spend.payments, charge.category, charge.base_amount)
    return charged_payment_ids(charges)


def _add_logged_expenses(
    db: Session,
    user_id: str,
    year: int,
    month: int,
    base: str,
    snapshot: dict | None,
    charged_ids: set[str],
    spend: _CategorySpend,
) -> None:
    first, last = month_bounds(year, month)
    rows = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.kind == TransactionKind.expense.value,
        Transaction.occurred_on.between(first, last),
    ).all()
    for row in rows:
        if row.recurring_payment_id is not None and str(row.recurring_payment_id) in charged_ids:
            continue
        spend.add(spend.logged, _category_value(row.category), amount_in_base(row, base, snapshot))


def limit_in_base(budget: Budget, base: str, snapshot: dict | None) -> Decimal | None:
    """The budget's limit in today's base currency, or None when no valid rate exists."""
    limit = Decimal(budget.monthly_limit)
    if budget.currency == base:
        return limit
    rate = (snapshot or {}).get("rates", {}).get(budget.currency)
    if not isinstance(rate, (int, float)) or rate <= 0:
        return None
    return (limit / Decimal(str(rate))).quantize(CENTS)


def _money(value: Decimal | None) -> float | None:
    return None if value is None else float(value.quantize(CENTS))


def _budget_row(budget: Budget, spend: _CategorySpend, base: str, snapshot: dict | None) -> dict:
    category = _category_value(budget.category)
    logged = spend.logged.get(category, ZERO)
    payments = spend.payments.get(category, ZERO)
    spent = logged + payments
    limit = limit_in_base(budget, base, snapshot)
    share = None if limit is None else (spent / limit).quantize(SHARE_PLACES)
    over = None if limit is None else spent > limit
    return {
        "id": str(budget.id),
        "category": category,
        "monthly_limit": float(budget.monthly_limit),
        "currency": budget.currency,
        "limit_in_base": _money(limit),
        "spent": _money(spent),
        "spent_logged": _money(logged),
        "spent_payments": _money(payments),
        "left": None if limit is None else _money(limit - spent),
        "share_used": None if share is None else float(share),
        "over": over,
        "near": None if share is None else (not over and share >= NEAR_LIMIT_SHARE),
        "unconverted_count": spend.unconverted.get(category, 0),
    }


def budget_status(db: Session, user_id: str, year: int, month: int) -> dict:
    """Every budget's limit, spending and what is left, in the user's base currency.

    Amounts without a valid conversion are counted in ``unconverted_count`` and
    left out of ``spent``; a limit that cannot be converted leaves ``left``,
    ``share_used``, ``over`` and ``near`` as None. Nothing is treated as 1:1.
    """
    base = base_currency_for(db, user_id)
    snapshot = get_cached_rate_snapshot(base, db)
    budgets = db.query(Budget).filter(Budget.user_id == user_id).all()

    spend = _CategorySpend()
    if budgets:
        charged_ids = _add_tracked_payments(db, user_id, year, month, spend)
        _add_logged_expenses(db, user_id, year, month, base, snapshot, charged_ids, spend)

    snapshot_time = _snapshot_time(snapshot)
    return {
        "month": f"{year:04d}-{month:02d}",
        "base_currency": base,
        "budgets": sorted(
            (_budget_row(budget, spend, base, snapshot) for budget in budgets),
            key=lambda row: row["category"],
        ),
        "rate_as_of": snapshot_time.isoformat() if snapshot_time else None,
        "rate_stale": bool(snapshot and snapshot.get("stale")),
    }
