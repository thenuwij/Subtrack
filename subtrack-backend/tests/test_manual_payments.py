import os
import unittest
from datetime import date, datetime
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import BillingCycle, Category, Subscription, Transaction, UserPreference  # noqa: E402
from app.routers.budgets import BudgetCreate, create_budget  # noqa: E402
from app.routers.subscriptions import (  # noqa: E402
    MarkPaidRequest,
    SubscriptionCreate,
    create_subscription,
    get_manual_due,
    mark_paid,
)
from app.routers.transactions import delete_transaction, get_transaction_summary, list_transactions  # noqa: E402
from app.services.budgets import budget_status  # noqa: E402

RATES = {"base": "AUD", "rates": {"USD": 0.5}, "stale": False, "fetched_at": "2026-11-03T00:00:00"}
# Monday 9 November 2026; "today" in these tests is Thursday 12 November.
MONDAY = date(2026, 11, 9)
THURSDAY = date(2026, 11, 12)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 11, 12, 12, 0, tzinfo=tz)


class ManualPaymentTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(UserPreference(user_id="owner", base_currency="AUD", timezone="UTC"))
        self.db.commit()
        for target in (
            "app.routers.rates.get_cached_rate_snapshot",
            "app.services.transactions.get_cached_rate_snapshot",
            "app.services.budgets.get_cached_rate_snapshot",
            "app.agent.finance.get_cached_rate_snapshot",
        ):
            patcher = patch(target, return_value=RATES)
            patcher.start()
            self.addCleanup(patcher.stop)
        clock = patch("app.routers.subscriptions.datetime", FrozenDatetime)
        clock.start()
        self.addCleanup(clock.stop)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def rent(self, method="manual"):
        row = Subscription(
            id=uuid4(), user_id="owner", name="Rent", category=Category.housing,
            amount=500.0, currency="AUD", cycle=BillingCycle.weekly,
            interval_unit="week", interval_count=1, is_active=True,
            next_due=datetime(2026, 11, 9), payment_method=method,
        )
        self.db.add(row)
        self.db.commit()
        return row

    def summary(self):
        return get_transaction_summary(month="2026-11", user_id="owner", db=self.db)

    def mark(self, rent, due=MONDAY, paid_on=THURSDAY, **extra):
        return mark_paid(rent.id, MarkPaidRequest(due_date=due, paid_on=paid_on, **extra), user_id="owner", db=self.db)

    def test_new_payments_default_to_automatic(self):
        created = create_subscription(
            SubscriptionCreate(name="Netflix", category="streaming", amount=22, cycle="monthly",
                               next_due=datetime(2026, 11, 15)),
            user_id="owner", db=self.db,
        )
        self.assertEqual(created["payment_method"], "automatic")

    def test_automatic_rent_still_counts_every_scheduled_charge(self):
        self.rent(method="automatic")
        self.assertEqual(self.summary()["expenses"], 2500.0)  # five Mondays this month

    def test_unpaid_manual_rent_is_not_counted(self):
        self.rent()
        create_budget(BudgetCreate(category="housing", monthly_limit="3000.00"), user_id="owner", db=self.db)

        rows = list_transactions(month="2026-11", kind=None, category=None, user_id="owner", db=self.db)
        budgets = budget_status(self.db, "owner", 2026, 11)["budgets"]

        self.assertEqual(rows, [])
        self.assertEqual(self.summary()["expenses"], 0.0)
        self.assertEqual(budgets[0]["spent"], 0.0)

    def test_marking_paid_creates_one_entry_counted_once(self):
        rent = self.rent()
        create_budget(BudgetCreate(category="housing", monthly_limit="3000.00"), user_id="owner", db=self.db)

        entry = self.mark(rent, amount="500.00")

        self.assertEqual(entry["occurred_on"], "2026-11-12")
        self.assertEqual(entry["note"], "Rent payment")
        self.assertEqual(entry["recurring_payment_id"], str(rent.id))
        rows = list_transactions(month="2026-11", kind=None, category=None, user_id="owner", db=self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.summary()["expenses"], 500.0)
        self.assertEqual(budget_status(self.db, "owner", 2026, 11)["budgets"][0]["spent"], 500.0)

    def test_amount_and_currency_default_to_the_payments(self):
        entry = self.mark(self.rent())
        self.assertEqual((entry["amount"], entry["currency"], entry["base_amount"]), (500.0, "AUD", 500.0))

    def test_foreign_amount_without_a_rate_stays_unconverted(self):
        entry = self.mark(self.rent(), amount="10.00", currency="GBP")
        self.assertIsNone(entry["base_amount"])

    def test_second_mark_for_same_due_date_is_rejected_and_leaves_manual_due(self):
        rent = self.rent()
        self.mark(rent)

        with self.assertRaises(HTTPException) as raised:
            self.mark(rent)

        self.assertEqual(raised.exception.status_code, 409)
        due_dates = [row["due_date"] for row in get_manual_due(user_id="owner", db=self.db)]
        self.assertNotIn("2026-11-09", due_dates)

    def test_unpaid_past_due_date_is_overdue(self):
        rent = self.rent()
        due = {row["due_date"]: row for row in get_manual_due(user_id="owner", db=self.db)}

        self.assertTrue(due["2026-11-09"]["overdue"])
        self.assertFalse(due["2026-11-16"]["overdue"])
        self.assertNotIn("2026-11-23", due)
        self.assertEqual(due["2026-11-09"]["payment_id"], str(rent.id))
        self.assertEqual(due["2026-11-09"]["amount"], 500.0)

    def test_due_date_is_the_users_local_date(self):
        self.db.query(UserPreference).filter_by(user_id="owner").update({"timezone": "Australia/Sydney"})
        self.db.commit()
        rent = self.rent()
        # 00:30 on Monday 16 November in Sydney is still Sunday in UTC.
        rent.next_due = datetime(2026, 11, 15, 13, 30)
        self.db.commit()

        due = {row["due_date"]: row for row in get_manual_due(user_id="owner", db=self.db)}

        self.assertIn("2026-11-16", due)
        self.assertNotIn("2026-11-15", due)
        self.assertTrue(due["2026-11-09"]["overdue"])
        self.mark(rent, due=date(2026, 11, 16))
        self.assertNotIn("2026-11-16", [row["due_date"] for row in get_manual_due(user_id="owner", db=self.db)])

    def test_deleting_the_entry_undoes_the_mark(self):
        rent = self.rent()
        entry = self.mark(rent)
        delete_transaction(UUID(entry["id"]), user_id="owner", db=self.db)

        due_dates = [row["due_date"] for row in get_manual_due(user_id="owner", db=self.db)]
        self.assertIn("2026-11-09", due_dates)

    def test_automatic_payment_cannot_be_marked_paid(self):
        with self.assertRaises(HTTPException) as raised:
            self.mark(self.rent(method="automatic"))
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(self.db.query(Transaction).count(), 0)


if __name__ == "__main__":
    unittest.main()
