import os
import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.gmail.analyzer import DetectedSubscription as Found  # noqa: E402
from app.models import BillingCycle, Category, ChangeKind, Subscription, SubscriptionChange  # noqa: E402
from app.routers.gmail import _apply_detections  # noqa: E402


class VariableBillTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.origin = Subscription(
            user_id="owner", name="Origin Energy electricity", category=Category.utilities,
            amount=171.68, currency="AUD", cycle=BillingCycle.monthly, interval_unit="month",
            interval_count=1, amount_type="variable", is_active=True,
            source_domain="originenergy.com.au", source_key="origin-energy-electricity",
        )
        self.db.add(self.origin)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def bill(self, amount, when, **extra):
        found = Found(
            sender_domain="originenergy.com.au", merchant="Origin Energy electricity",
            product_key="origin-energy-electricity", interval_unit="month", interval_count=1,
            cadence_confidence="medium", amount=amount, currency="AUD", cancelled=False,
            amount_type="variable", category="utilities", confidence="medium", charge_count=1,
            last_successful_charge_at=when, **extra,
        )
        rows = []
        _apply_detections(self.db, "owner", [self.origin], rows, [found])
        self.db.commit()
        return rows

    def test_new_bill_updates_the_estimate_without_a_review_item(self):
        rows = self.bill(140.0, datetime(2026, 11, 2))

        self.assertEqual(rows, [])
        self.assertAlmostEqual(self.origin.amount, round((171.68 + 140.0) / 2, 2))
        self.assertEqual(self.origin.bill_history, [171.68, 140.0])

    def test_estimate_is_the_average_of_the_last_three_bills(self):
        self.bill(140.0, datetime(2026, 9, 2))
        self.bill(200.0, datetime(2026, 10, 2))
        self.bill(110.0, datetime(2026, 11, 2))

        self.assertEqual(self.origin.bill_history, [140.0, 200.0, 110.0])
        self.assertAlmostEqual(self.origin.amount, 150.0)

    def test_same_bill_seen_again_is_not_counted_twice(self):
        self.bill(140.0, datetime(2026, 11, 2))
        self.bill(140.0, datetime(2026, 11, 2))

        self.assertEqual(self.origin.bill_history, [171.68, 140.0])

    def test_update_shows_in_what_changed(self):
        self.bill(140.0, datetime(2026, 11, 2))
        change = self.db.query(SubscriptionChange).one()
        self.assertEqual(change.kind, ChangeKind.price_change)

    def test_bill_due_date_is_saved(self):
        self.bill(140.0, datetime(2026, 11, 2), next_due=datetime(2099, 11, 20))
        self.assertEqual(self.origin.next_due, datetime(2099, 11, 20))

    def test_fixed_price_payments_still_go_to_review(self):
        self.origin.amount_type = "fixed"
        self.db.commit()
        rows = self.bill(140.0, datetime(2026, 11, 2))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].existing_subscription_id, self.origin.id)


if __name__ == "__main__":
    unittest.main()
