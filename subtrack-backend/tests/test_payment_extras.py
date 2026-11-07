import os
import unittest
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.gmail.analyzer import DetectedSubscription as Found  # noqa: E402
from app.gmail.rules import detect  # noqa: E402
from app.gmail.scanner import ReceiptCandidate  # noqa: E402
from app.models import (  # noqa: E402
    BillingCycle,
    Category,
    DetectedSubscription,
    DetectionStatus,
    PaymentExtra,
    SenderLink,
    Subscription,
)
from app.routers import detected as detected_router  # noqa: E402
from app.routers.gmail import _apply_detections  # noqa: E402
from app.services.payment_links import load_links, merchant_key, name_match  # noqa: E402


class NameMatchTests(unittest.TestCase):
    def sub(self, name):
        return Subscription(name=name)

    def test_finding_name_containing_tracked_name_matches(self):
        gym = self.sub("Anytime Fitness")
        self.assertIs(name_match("Anytime Fitness membership", [gym, self.sub("Netflix")]), gym)

    def test_unrelated_names_do_not_match(self):
        self.assertIsNone(name_match("F45 Training membership", [self.sub("Anytime Fitness")]))

    def test_ambiguous_match_is_not_guessed(self):
        self.assertIsNone(name_match("Apple", [self.sub("Apple Music"), self.sub("Apple iCloud")]))

    def test_key_ignores_billing_words_and_order(self):
        self.assertEqual(merchant_key("Anytime Fitness membership"), merchant_key("fitness anytime"))

    def test_billing_platform_is_never_decided_by_rules_alone(self):
        emails = [
            ReceiptCandidate(f"m{i}", "debitsuccess.com", "Debitsuccess", "Receipt", d, 24.95, "AUD", "high")
            for i, d in enumerate(["2026-08-07", "2026-08-21", "2026-09-04"])
        ]
        self.assertIsNone(detect("debitsuccess.com", emails))


class SamePaymentTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.gym = Subscription(
            user_id="owner", name="Anytime Fitness", category=Category.fitness, amount=24.95,
            currency="AUD", cycle=BillingCycle.weekly, interval_unit="week", interval_count=2,
            is_active=True,
        )
        self.db.add(self.gym)
        self.db.commit()
        self.finding = DetectedSubscription(
            user_id="owner", merchant="Anytime Fitness membership", sender_domain="debitsuccess.com",
            product_key="anytime-fitness-membership", category=Category.fitness,
            cycle=BillingCycle.monthly, cadence_confidence="unknown", amount=32.45, currency="AUD",
            charge_count=4, last_charge_at=datetime(2026, 10, 30), status=DetectionStatus.pending,
        )
        self.db.add(self.finding)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def confirm(self, kind):
        return detected_router.confirm_same_payment(
            self.finding.id,
            detected_router.SamePaymentRequest(subscription_id=self.gym.id, kind=kind),
            user_id="owner",
            db=self.db,
        )

    def test_review_list_suggests_the_matching_payment_by_name(self):
        rows = detected_router.list_detections(user_id="owner", db=self.db)
        self.assertEqual(rows[0]["similar_subscription_id"], str(self.gym.id))

    def test_late_fee_records_only_the_extra_and_keeps_the_price(self):
        result = self.confirm("extra")

        self.assertEqual(result["extra_amount"], 7.5)
        extra = self.db.query(PaymentExtra).one()
        self.assertEqual((float(extra.amount), extra.reason), (7.5, "late_fee"))
        self.assertEqual(extra.charged_at, datetime(2026, 10, 30))
        self.db.refresh(self.gym)
        self.assertEqual(self.gym.amount, 24.95)
        self.db.refresh(self.finding)
        self.assertEqual(self.finding.status, DetectionStatus.approved)

    def test_sender_and_business_are_remembered(self):
        self.confirm("regular")
        link = self.db.query(SenderLink).one()
        self.assertEqual((link.sender_domain, link.merchant_key), ("debitsuccess.com", "anytime-fitness"))

    def test_extra_must_be_more_than_the_usual_price(self):
        self.finding.amount = 24.95
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            self.confirm("extra")
        self.assertEqual(caught.exception.status_code, 422)

    def test_new_price_updates_the_payment(self):
        self.confirm("new_price")
        self.db.refresh(self.gym)
        self.assertEqual(self.gym.amount, 32.45)

    def test_next_scan_links_the_same_sender_and_business_on_its_own(self):
        self.confirm("regular")
        later = Found(
            sender_domain="debitsuccess.com", merchant="Anytime Fitness membership",
            product_key="anytime-fitness-membership", cadence_confidence="unknown",
            amount=32.45, currency="AUD", cancelled=False, category="fitness",
            confidence="medium", charge_count=1,
        )
        rows = []
        _apply_detections(self.db, "owner", [self.gym], rows, [later], load_links(self.db, "owner"))
        self.assertEqual(rows[-1].existing_subscription_id, self.gym.id)

    def test_a_different_gym_on_the_same_platform_is_not_linked(self):
        self.confirm("regular")
        other = Found(
            sender_domain="debitsuccess.com", merchant="F45 Training", product_key="f45-training",
            cadence_confidence="unknown", amount=60.0, currency="AUD", cancelled=False,
            category="fitness", confidence="medium", charge_count=1,
        )
        rows = []
        _apply_detections(self.db, "owner", [self.gym], rows, [other], load_links(self.db, "owner"))
        self.assertIsNone(rows[-1].existing_subscription_id)


if __name__ == "__main__":
    unittest.main()


class SameFindingTests(unittest.TestCase):
    def test_same_items_written_differently(self):
        from app.services.payment_links import is_same_finding
        self.assertTrue(is_same_finding("Google One 100 GB", "google-one-100-gb", "Google One 100GB", "google-one-100gb"))
        self.assertTrue(is_same_finding("ChatGPT Plus", "chatgpt-plus", "ChatGPT Plus", "openai-chatgpt-plus"))
        self.assertTrue(is_same_finding("Origin Energy", "origin-energy", "Origin Energy electricity", "origin-energy-electricity"))

    def test_different_items_stay_apart(self):
        from app.services.payment_links import is_same_finding
        self.assertFalse(is_same_finding("Apple", "apple-music", "Apple", "apple-icloud"))
        self.assertFalse(is_same_finding("TikTok LIVE Super Fan", "tiktok-live-super-fan", "TikTok Sarah", "tiktok-sarah"))
        self.assertFalse(is_same_finding("Google One", None, "Netflix", None))
