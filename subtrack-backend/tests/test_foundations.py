import os
import unittest
from datetime import date
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import BillingCycle, Category, Subscription, Transaction, UserPreference  # noqa: E402
from app.routers.preferences import PreferenceUpdate, get_preferences, update_preferences  # noqa: E402
from app.services.transaction_duplicates import find_possible_duplicates  # noqa: E402


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_transaction(self, user_id="owner", name="Woolworths", amount="42.10", day=10):
        row = Transaction(
            user_id=user_id, kind="expense", name=name, amount=Decimal(amount),
            currency="AUD", category=Category.food, occurred_on=date(2026, 11, day),
        )
        self.db.add(row)
        self.db.commit()
        return row

    def find(self, name="Woolworths", amount="42.00", day=11):
        return find_possible_duplicates(
            self.db, "owner", name=name, amount=Decimal(amount),
            currency="AUD", occurred_on=date(2026, 11, day),
        )

    def test_new_users_and_existing_users_get_every_feature(self):
        self.db.add(UserPreference(user_id="existing"))
        self.db.commit()

        self.assertEqual(
            get_preferences(user_id="new", db=self.db)["enabled_features"],
            ["spending", "payments", "goals", "workspace"],
        )
        self.assertEqual(
            get_preferences(user_id="existing", db=self.db)["enabled_features"],
            ["spending", "payments", "goals", "workspace"],
        )

    def test_chosen_features_are_saved_in_a_stable_order(self):
        update_preferences(
            PreferenceUpdate(enabled_features=["workspace", "payments", "payments"]),
            user_id="owner", db=self.db,
        )

        self.assertEqual(
            get_preferences(user_id="owner", db=self.db)["enabled_features"],
            ["payments", "workspace"],
        )

    def test_feature_list_rejects_unknown_and_empty_choices(self):
        for value in (["banking"], []):
            with self.assertRaises(ValidationError):
                PreferenceUpdate(enabled_features=value)

    def test_similar_name_amount_and_close_date_is_flagged(self):
        existing = self.add_transaction()

        matches = self.find(name="WOOLWORTHS 1234")

        self.assertEqual([(m.kind, m.id) for m in matches], [("transaction", existing.id)])

    def test_far_date_different_amount_or_other_user_is_not_flagged(self):
        self.add_transaction(day=1)
        self.add_transaction(amount="90.00")
        self.add_transaction(user_id="other")

        self.assertEqual(self.find(), [])

    def test_tracked_payment_with_same_name_and_amount_is_flagged(self):
        payment = Subscription(
            user_id="owner", name="AGL Energy", category=Category.utilities,
            amount=180.0, currency="AUD", cycle=BillingCycle.monthly,
            interval_unit="month", interval_count=1, is_active=True,
        )
        self.db.add(payment)
        self.db.commit()

        matches = self.find(name="AGL", amount="182.50")

        self.assertEqual([(m.kind, m.id) for m in matches], [("payment", payment.id)])


if __name__ == "__main__":
    unittest.main()
