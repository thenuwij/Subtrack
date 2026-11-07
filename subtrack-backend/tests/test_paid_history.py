import os
import unittest
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402
    BillingCycle,
    Category,
    GmailReceipt,
    PaymentExtra,
    SenderLink,
    Subscription,
    UserPreference,
)
from app.services.paid_history import paid_history  # noqa: E402

TODAY = date(2026, 11, 7)


class PaidHistoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(UserPreference(user_id="owner", base_currency="AUD"))
        self.netflix = self.sub("Netflix", 20.99, "netflix.com", datetime(2026, 11, 12))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def sub(self, name, amount, domain, next_due, created=datetime(2026, 1, 1)):
        sub = Subscription(
            user_id="owner", name=name, category=Category.streaming, amount=amount, currency="AUD",
            cycle=BillingCycle.monthly, interval_unit="month", interval_count=1, next_due=next_due,
            is_active=True, source_domain=domain, created_at=created,
        )
        self.db.add(sub)
        self.db.flush()
        return sub

    def receipt(self, domain, when, amount, merchant=None, message=None):
        self.db.add(GmailReceipt(
            user_id="owner", gmail_message_id=message or f"{domain}-{when}", intermediary=domain,
            merchant=merchant, amount=amount, currency="AUD", received_on=when,
        ))
        self.db.commit()

    def history(self):
        return paid_history(self.db, "owner", months=3, today=TODAY)["payments"]

    def test_due_date_with_a_receipt_is_confirmed_and_without_one_is_expected(self):
        self.receipt("netflix.com", date(2026, 10, 13), 20.99)
        rows = [(r["date"], r["status"]) for r in self.history() if r["name"] == "Netflix"]
        self.assertIn(("2026-10-13", "confirmed"), rows)
        self.assertIn(("2026-09-12", "expected"), rows)
        self.assertNotIn("2026-11-12", [d for d, _ in rows])  # future dates aren't history

    def test_nothing_is_expected_before_the_payment_was_tracked(self):
        self.netflix.created_at = datetime(2026, 10, 20)
        self.db.commit()
        self.assertEqual(
            [r["status"] for r in self.history() if r["name"] == "Netflix"], [],
        )

    def test_same_sender_two_payments_match_by_amount(self):
        self.sub("Apple Music", 14.99, "apple.com", datetime(2026, 11, 20))
        self.sub("iCloud", 4.49, "apple.com", datetime(2026, 11, 20))
        self.receipt("apple.com", date(2026, 10, 20), 4.49, message="a1")
        confirmed = [(r["name"], r["status"]) for r in self.history() if r["date"] == "2026-10-20"]
        self.assertIn(("iCloud", "confirmed"), confirmed)
        self.assertIn(("Apple Music", "expected"), confirmed)

    def test_billing_platform_receipt_uses_the_saved_link(self):
        gym = self.sub("Anytime Fitness", 24.95, None, datetime(2026, 11, 13))
        self.db.add(SenderLink(user_id="owner", sender_domain="debitsuccess.com",
                               merchant_key="anytime-fitness", subscription_id=gym.id))
        self.receipt("debitsuccess.com", date(2026, 10, 30), 32.45, merchant="Anytime Fitness membership")
        rows = [(r["name"], r["amount"], r["status"]) for r in self.history() if r["date"] == "2026-10-30"]
        self.assertEqual(rows, [("Anytime Fitness", 32.45, "confirmed")])

    def test_late_fees_are_listed(self):
        self.db.add(PaymentExtra(user_id="owner", subscription_id=self.netflix.id, amount=7.5,
                                 currency="AUD", charged_at=datetime(2026, 10, 30), reason="late_fee"))
        self.db.commit()
        kinds = [r["kind"] for r in self.history() if r["date"] == "2026-10-30"]
        self.assertEqual(kinds, ["late_fee"])

    def test_unknown_sender_receipts_are_ignored(self):
        self.receipt("randomshop.com", date(2026, 10, 2), 50.0)
        self.assertNotIn("2026-10-02", [r["date"] for r in self.history()])


if __name__ == "__main__":
    unittest.main()
