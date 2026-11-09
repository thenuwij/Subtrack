import os
import unittest
from datetime import date, datetime
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402
    BillingCycle,
    Budget,
    Category,
    PaymentExtra,
    Subscription,
    Transaction,
    UserPreference,
)
from app.routers.budgets import (  # noqa: E402
    BudgetCreate,
    BudgetUpdate,
    create_budget,
    delete_budget,
    get_budget_status,
    update_budget,
)

# One AUD buys 0.5 USD, so 10 USD is 20 AUD. There is no GBP rate.
RATES = {"base": "AUD", "rates": {"USD": 0.5}, "stale": False, "fetched_at": "2026-11-03T00:00:00"}


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(UserPreference(user_id="owner", base_currency="AUD", timezone="Australia/Sydney"))
        self.db.commit()
        for target in (
            "app.routers.rates.get_cached_rate_snapshot",
            "app.services.budgets.get_cached_rate_snapshot",
            "app.services.transactions.get_cached_rate_snapshot",
            "app.agent.finance.get_cached_rate_snapshot",
        ):
            patcher = patch(target, return_value=RATES)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def budget(self, category="food", limit="100.00", user_id="owner"):
        return create_budget(
            BudgetCreate(category=category, monthly_limit=limit), user_id=user_id, db=self.db,
        )

    def expense(self, amount, category=Category.food, currency="AUD", day=10, payment=None, user_id="owner"):
        self.db.add(Transaction(
            user_id=user_id, kind="expense", name="Spend", amount=amount, currency=currency,
            category=category, occurred_on=date(2026, 11, day),
            recurring_payment_id=payment.id if payment else None,
        ))
        self.db.commit()

    def payment(self, amount, category=Category.utilities, currency="AUD", unit="month", due=datetime(2026, 11, 15)):
        row = Subscription(
            id=uuid4(), user_id="owner", name="AGL Energy", category=category,
            amount=amount, currency=currency, cycle=BillingCycle.monthly,
            interval_unit=unit, interval_count=1, is_active=True,
            next_due=due,
        )
        self.db.add(row)
        self.db.commit()
        return row

    def status(self, month="2026-11", user_id="owner"):
        result = get_budget_status(month=month, user_id=user_id, db=self.db)
        return {row["category"]: row for row in result["budgets"]}

    def test_spent_combines_logged_expenses_and_tracked_payments(self):
        self.budget("utilities", "300.00")
        self.payment(180)
        self.expense(40, category=Category.utilities)
        self.expense(15, category=Category.food)

        row = self.status()["utilities"]

        self.assertEqual(row["spent"], 220.0)
        self.assertEqual(row["spent_payments"], 180.0)
        self.assertEqual(row["spent_logged"], 40.0)
        self.assertEqual(row["left"], 80.0)

    def test_logged_expense_linked_to_a_charged_payment_is_counted_once(self):
        self.budget("utilities", "300.00")
        bill = self.payment(180)
        self.expense(180, category=Category.utilities, payment=bill)

        self.assertEqual(self.status()["utilities"]["spent"], 180.0)

    def test_linked_expense_counts_when_its_payment_is_not_charged_that_month(self):
        self.budget("utilities", "300.00")
        bill = self.payment(180, unit="year", due=datetime(2026, 12, 15))
        self.expense(60, category=Category.utilities, payment=bill)

        row = self.status()["utilities"]

        self.assertEqual((row["spent_logged"], row["spent_payments"]), (60.0, 0.0))

    def test_payment_extras_count_towards_the_payment_category(self):
        self.budget("utilities", "300.00")
        bill = self.payment(180)
        self.db.add(PaymentExtra(
            user_id="owner", subscription_id=bill.id, amount=12, currency="AUD",
            charged_at=datetime(2026, 11, 20), reason="late_fee",
        ))
        self.db.commit()

        self.assertEqual(self.status()["utilities"]["spent_payments"], 192.0)

    def test_yearly_payment_charged_in_another_month_is_not_counted(self):
        self.budget("utilities", "300.00")
        self.payment(180, unit="year")

        self.assertEqual(self.status("2026-10")["utilities"]["spent_payments"], 0.0)

    def test_over_and_near_flags(self):
        self.budget("food", "100.00")
        self.budget("transport", "100.00")
        self.budget("shopping", "100.00")
        self.expense(101, category=Category.food)
        self.expense(80, category=Category.transport)
        self.expense(79.99, category=Category.shopping)

        rows = self.status()

        self.assertEqual((rows["food"]["over"], rows["food"]["near"]), (True, False))
        self.assertEqual((rows["transport"]["over"], rows["transport"]["near"]), (False, True))
        self.assertEqual(rows["transport"]["share_used"], 0.8)
        self.assertEqual((rows["shopping"]["over"], rows["shopping"]["near"]), (False, False))

    def test_unconverted_amounts_are_reported_not_counted_one_to_one(self):
        self.budget("food", "100.00")
        self.expense(10, currency="USD")
        self.expense(30, currency="GBP")

        row = self.status()["food"]

        self.assertEqual(row["spent"], 20.0)
        self.assertEqual(row["unconverted_count"], 1)

    def test_limit_saved_in_an_older_base_currency_is_converted_or_left_unconverted(self):
        self.budget("food", "10.00")
        self.budget("transport", "10.00")
        self.db.query(Budget).filter(Budget.category == Category.food).update({"currency": "USD"})
        self.db.query(Budget).filter(Budget.category == Category.transport).update({"currency": "GBP"})
        self.db.commit()

        rows = self.status()

        self.assertEqual(rows["food"]["limit_in_base"], 20.0)
        self.assertIsNone(rows["transport"]["limit_in_base"])
        self.assertIsNone(rows["transport"]["left"])
        self.assertIsNone(rows["transport"]["over"])

    def test_budget_is_saved_in_the_users_base_currency(self):
        created = self.budget()

        self.assertEqual(created["currency"], "AUD")
        with self.assertRaises(ValidationError):
            BudgetCreate(category="food", monthly_limit="10", currency="USD")

    def test_limit_must_be_positive_and_in_cents(self):
        for limit in ("0", "-5", "1.234", "NaN", "1000000.01"):
            with self.assertRaises(ValidationError):
                BudgetCreate(category="food", monthly_limit=limit)

    def test_one_budget_per_category_per_user(self):
        self.budget("food")
        self.budget("food", user_id="other")
        with self.assertRaises(HTTPException) as caught:
            self.budget("food")
        self.assertEqual(caught.exception.status_code, 409)

        transport = self.budget("transport")
        with self.assertRaises(HTTPException) as caught:
            update_budget(UUID(transport["id"]), BudgetUpdate(category="food"), user_id="owner", db=self.db)
        self.assertEqual(caught.exception.status_code, 409)

    def test_update_and_delete(self):
        created = self.budget()

        updated = update_budget(
            UUID(created["id"]), BudgetUpdate(monthly_limit="250.00"), user_id="owner", db=self.db,
        )
        delete_budget(UUID(created["id"]), user_id="owner", db=self.db)

        self.assertEqual(updated["monthly_limit"], 250.0)
        self.assertEqual(self.status(), {})

    def test_other_users_budgets_are_hidden_and_return_404(self):
        theirs = self.budget(user_id="other")
        self.expense(50, user_id="other")

        self.assertEqual(self.status(), {})
        for action in (
            lambda: update_budget(UUID(theirs["id"]), BudgetUpdate(monthly_limit="5"), user_id="owner", db=self.db),
            lambda: delete_budget(UUID(theirs["id"]), user_id="owner", db=self.db),
        ):
            with self.assertRaises(HTTPException) as caught:
                action()
            self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
