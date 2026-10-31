import os
import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402
    BillingCycle,
    Category,
    SafeToSpendProfile,
    Subscription,
    UserPreference,
)
from app.routers.safe_to_spend import SafeToSpendProfileUpdate, put_profile  # noqa: E402
from app.services.safe_to_spend import can_i_afford, safe_to_spend  # noqa: E402

NOW = datetime(2026, 11, 3, 2, 0)
RATES = {"rates": {"USD": 0.5}, "stale": False, "fetched_at": "2026-11-03T00:00:00"}


class SafeToSpendTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        patcher = patch("app.agent.finance.get_cached_rate_snapshot", return_value=RATES)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.db.add(UserPreference(user_id="owner", base_currency="AUD", timezone="Australia/Sydney"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_profile(self, **overrides):
        values = {
            "user_id": "owner",
            "balance": Decimal("620.00"),
            "currency": "AUD",
            "balance_as_of": NOW,
            "pay_anchor_on": date(2026, 11, 10),
            "pay_interval_unit": "week",
            "pay_interval_count": 2,
            "buffer": Decimal("50.00"),
        }
        self.db.add(SafeToSpendProfile(**{**values, **overrides}))
        self.db.commit()

    def add_payment(self, name, amount, next_due, **overrides):
        values = {
            "user_id": "owner",
            "name": name,
            "category": list(Category)[0],
            "amount": amount,
            "currency": "AUD",
            "cycle": BillingCycle.monthly,
            "interval_unit": "month",
            "interval_count": 1,
            "next_due": next_due,
        }
        self.db.add(Subscription(**{**values, **overrides}))
        self.db.commit()

    def test_subtracts_commitments_and_buffer_and_splits_by_day(self):
        self.add_profile()
        self.add_payment("Rent", 400, datetime(2026, 11, 5))
        self.add_payment("Streaming", 30, datetime(2026, 11, 8))

        result = safe_to_spend(self.db, "owner", now=NOW)

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["safe_to_spend"], 140.0)
        self.assertEqual(result["days_until_payday"], 7)
        self.assertEqual(result["per_day"], 20.0)
        self.assertEqual(result["committed"], 430.0)

    def test_payment_due_on_payday_counts_but_later_payment_does_not(self):
        self.add_profile()
        self.add_payment("On payday", 100, datetime(2026, 11, 10))
        self.add_payment("After payday", 100, datetime(2026, 11, 11))

        result = safe_to_spend(self.db, "owner", now=NOW)

        self.assertEqual(result["committed"], 100.0)

    def test_payday_bill_stored_at_noon_utc_counts_in_new_zealand(self):
        self.db.get(UserPreference, "owner").timezone = "Pacific/Auckland"
        self.add_profile()
        self.add_payment("On payday", 100, datetime(2026, 11, 10, 12, 0))
        self.add_payment("Day before balance", 100, datetime(2026, 11, 2, 12, 0), interval_unit="year", cycle=BillingCycle.yearly)

        self.assertEqual(safe_to_spend(self.db, "owner", now=NOW)["committed"], 100.0)

    def test_payment_due_on_balance_date_counts_as_unpaid(self):
        self.add_profile()
        self.add_payment("Due today", 20, datetime(2026, 11, 3))

        self.assertEqual(safe_to_spend(self.db, "owner", now=NOW)["committed"], 20.0)

    def test_shortfall_never_shows_a_negative_safe_amount(self):
        self.add_profile(balance=Decimal("100.00"))
        self.add_payment("Rent", 400, datetime(2026, 11, 5))

        result = safe_to_spend(self.db, "owner", now=NOW)

        self.assertEqual(result["safe_to_spend"], 0.0)
        self.assertEqual(result["per_day"], 0.0)
        self.assertEqual(result["shortfall"], 350.0)

    def test_payment_due_after_an_old_balance_is_still_counted_with_a_warning(self):
        self.add_profile(balance_as_of=datetime(2026, 10, 29, 2, 0))
        self.add_payment("Missed", 30, datetime(2026, 10, 31))

        result = safe_to_spend(self.db, "owner", now=NOW)

        self.assertEqual(result["committed"], 30.0)
        self.assertTrue(any("few days old" in warning for warning in result["warnings"]))

    def test_balance_from_before_a_payday_gives_no_number(self):
        self.add_profile(
            balance_as_of=datetime(2026, 10, 25, 2, 0),
            pay_anchor_on=date(2026, 10, 27),
        )

        result = safe_to_spend(self.db, "owner", now=NOW)

        self.assertEqual(result["status"], "balance_outdated")
        self.assertIsNone(result["safe_to_spend"])
        self.assertEqual(result["next_payday"], "2026-11-10")

    def test_balance_updated_on_payday_targets_the_following_payday(self):
        self.add_profile(pay_anchor_on=date(2026, 11, 3))

        result = safe_to_spend(self.db, "owner", now=NOW)

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["next_payday"], "2026-11-17")

    def test_payday_uses_the_users_local_date(self):
        self.add_profile(pay_anchor_on=date(2026, 11, 4), balance_as_of=datetime(2026, 11, 3, 14, 0))

        result = safe_to_spend(self.db, "owner", now=datetime(2026, 11, 3, 14, 0))

        self.assertEqual(result["next_payday"], "2026-11-18")

    def test_missing_exchange_rate_gives_no_number_instead_of_one_to_one(self):
        self.add_profile()
        self.add_payment("Foreign", 10, datetime(2026, 11, 5), currency="JPY")

        result = safe_to_spend(self.db, "owner", now=NOW)

        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["safe_to_spend"])

    def test_foreign_payment_is_converted_with_the_shared_rate(self):
        self.add_profile()
        self.add_payment("Foreign", 10, datetime(2026, 11, 5), currency="USD")

        self.assertEqual(safe_to_spend(self.db, "owner", now=NOW)["committed"], 20.0)

    def test_payment_without_a_due_date_is_flagged(self):
        self.add_profile()
        self.add_payment("Unknown", 10, None)

        result = safe_to_spend(self.db, "owner", now=NOW)

        self.assertTrue(any("no due date" in warning for warning in result["warnings"]))

    def test_other_users_data_is_ignored(self):
        self.add_profile()
        self.add_payment("Other", 400, datetime(2026, 11, 5), user_id="other")

        self.assertEqual(safe_to_spend(self.db, "owner", now=NOW)["committed"], 0.0)

    def test_no_profile_asks_for_setup(self):
        self.assertEqual(safe_to_spend(self.db, "owner", now=NOW)["status"], "needs_setup")

    def test_can_i_afford_reports_what_is_left(self):
        self.add_profile()
        self.add_payment("Rent", 430, datetime(2026, 11, 5))

        yes = can_i_afford(self.db, "owner", Decimal("40.00"), now=NOW)
        no = can_i_afford(self.db, "owner", Decimal("141.00"), now=NOW)

        self.assertTrue(yes["affordable"])
        self.assertEqual(yes["left_after"], 100.0)
        self.assertEqual(yes["per_day_after"], 14.28)
        self.assertFalse(no["affordable"])
        self.assertEqual(no["left_after"], 0.0)

    def test_can_i_afford_has_no_answer_without_a_number(self):
        self.assertIsNone(can_i_afford(self.db, "owner", Decimal("5.00"), now=NOW)["affordable"])

    def test_editing_the_buffer_keeps_the_balance_date(self):
        old = datetime(2026, 1, 1)
        self.add_profile(balance_as_of=old)
        body = SafeToSpendProfileUpdate(
            balance=Decimal("620.00"),
            next_payday=date(2026, 11, 10),
            pay_interval_unit="week",
            pay_interval_count=2,
            buffer=Decimal("10.00"),
        )

        put_profile(body, user_id="owner", db=self.db)

        self.assertEqual(self.db.get(SafeToSpendProfile, "owner").balance_as_of, old)

    def test_changing_the_balance_refreshes_the_balance_date(self):
        old = datetime(2026, 1, 1)
        self.add_profile(balance_as_of=old)
        body = SafeToSpendProfileUpdate(
            balance=Decimal("500.00"),
            next_payday=date(2026, 11, 10),
            pay_interval_unit="week",
            pay_interval_count=2,
        )

        put_profile(body, user_id="owner", db=self.db)

        self.assertGreater(self.db.get(SafeToSpendProfile, "owner").balance_as_of, old)
