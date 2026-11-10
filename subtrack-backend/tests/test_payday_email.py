import os
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import jwt
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
    Category,
    EmailPreference,
    ReminderDelivery,
    SafeToSpendProfile,
    SetAside,
    Subscription,
    UserPreference,
)
from app.routers.email_reminders import EmailOptIn, get_email_preferences, set_email_preferences  # noqa: E402
from app.services.email_reminders import send_due  # noqa: E402
from app.services.email_text import email_safe_name  # noqa: E402

# Payday is Tue 10 Nov 2026 in Sydney (UTC+11). 21:00 UTC on 9 Nov is 8am there.
PAYDAY_MORNING = datetime(2026, 11, 9, 21, 0)
RATES = {"rates": {}, "stale": False, "fetched_at": "2026-11-09T00:00:00"}


class PaydayEmailTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        for target, value in (
            ("app.agent.finance.get_cached_rate_snapshot", RATES),
            ("app.services.email_reminders.settings.resend_api_key", "test"),
            ("app.services.email_reminders.settings.reminder_email_from", "Subtrack <hello@example.com>"),
            ("app.services.payday_message.settings.frontend_url", "https://subtrack.example"),
        ):
            patcher = patch(target, return_value=value) if target.endswith("snapshot") else patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.send = Mock(return_value=httpx.Response(200, request=httpx.Request("POST", "https://api.resend.com/emails")))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_user(self, user_id="owner", *, timezone="Australia/Sydney", payday=True, interval_count=2, **profile):
        self.db.add(UserPreference(user_id=user_id, base_currency="AUD", timezone=timezone))
        self.db.add(EmailPreference(user_id=user_id, email=f"{user_id}@example.com", enabled=False, payday_enabled=payday))
        values = {
            "user_id": user_id, "balance": None, "balance_as_of": None, "pay_amount": Decimal("1400.00"),
            "currency": "AUD", "pay_anchor_on": date(2026, 11, 10), "pay_interval_unit": "week",
            "pay_interval_count": interval_count, "buffer": Decimal("50.00"),
        }
        self.db.add(SafeToSpendProfile(**{**values, **profile}))
        self.db.add(Subscription(
            user_id=user_id, name="Phone", category=Category.phone_internet, amount=35, currency="AUD",
            cycle=BillingCycle.monthly, interval_unit="month", interval_count=1, next_due=datetime(2026, 11, 15),
        ))
        self.db.commit()

    def sent_at(self, now):
        return send_due(self.db, now=now, send=self.send)["sent"]

    def test_sends_once_on_payday_morning_with_the_engine_numbers(self):
        self.add_user()

        self.assertEqual(self.sent_at(PAYDAY_MORNING), 1)
        self.assertEqual(self.sent_at(PAYDAY_MORNING.replace(hour=23)), 0)

        payload = self.send.call_args.kwargs["json"]
        self.assertEqual(payload["to"], ["owner@example.com"])
        self.assertEqual(payload["subject"], "Payday: about A$93.92 a day until Tue 24 Nov")
        for line in (
            "Usual pay: A$1,400.00",
            "  - Phone, Sun 15 Nov: A$35.00",
            "Buffer: A$50.00",
            "Free to spend: A$1,315.00, about A$93.92 a day.",
            "https://subtrack.example/balance?from=payday",
            "https://subtrack.example/account#email-reminders",
        ):
            self.assertIn(line, payload["text"])
        self.assertEqual(self.db.query(ReminderDelivery).one().key, "payday/owner/2026-11-10")

    def test_waits_until_seven_in_the_morning_locally(self):
        self.add_user()

        self.assertEqual(self.sent_at(datetime(2026, 11, 9, 19, 0)), 0)  # 6am in Sydney
        self.assertEqual(self.sent_at(datetime(2026, 11, 9, 20, 0)), 1)  # 7am

    def test_uses_the_users_own_time_zone(self):
        self.add_user(timezone="UTC")

        self.assertEqual(self.sent_at(PAYDAY_MORNING), 0)  # still 9 Nov in UTC
        self.assertEqual(self.sent_at(datetime(2026, 11, 10, 7, 0)), 1)

    def test_fortnightly_skips_the_week_between_and_weekly_does_not(self):
        self.add_user("fortnightly")
        self.add_user("weekly", interval_count=1)

        send_due(self.db, now=datetime(2026, 11, 16, 21, 0), send=self.send)  # 17 Nov
        self.assertEqual([c.kwargs["json"]["to"] for c in self.send.call_args_list], [["weekly@example.com"]])
        self.send.reset_mock()
        send_due(self.db, now=datetime(2026, 11, 23, 21, 0), send=self.send)  # 24 Nov
        self.assertEqual(self.send.call_count, 2)

    def test_nothing_on_other_days(self):
        self.add_user()

        self.assertEqual(self.sent_at(datetime(2026, 11, 10, 21, 0)), 0)  # 11 Nov

    def test_respects_opt_out_and_never_sends_to_demo_accounts(self):
        self.add_user(payday=False)
        self.add_user("demo_abc")

        self.assertEqual(self.sent_at(PAYDAY_MORNING), 0)

    def test_without_a_number_it_asks_for_todays_balance(self):
        self.add_user(pay_amount=None, balance=Decimal("300.00"), balance_as_of=datetime(2026, 10, 30))

        self.assertEqual(self.sent_at(PAYDAY_MORNING), 1)
        payload = self.send.call_args.kwargs["json"]
        self.assertEqual(payload["subject"], "Payday: check what's free to spend")
        self.assertIn("Enter today's balance", payload["text"])

    def test_set_asides_are_listed(self):
        self.add_user()
        self.db.add(SetAside(user_id="owner", kind="pot", name="Eating out", amount_per_pay=60, currency="AUD"))
        self.db.commit()

        self.sent_at(PAYDAY_MORNING)

        text = self.send.call_args.kwargs["json"]["text"]
        self.assertIn("Set aside: A$60.00 (Eating out A$60.00)", text)
        self.assertIn("Free to spend: A$1,255.00", text)

    def test_a_shortfall_says_so(self):
        self.add_user(pay_amount=Decimal("60.00"))

        self.sent_at(PAYDAY_MORNING)

        self.assertEqual(self.send.call_args.kwargs["json"]["subject"], "Payday: your bills are A$25.00 more than you have")


class AlertTests(unittest.TestCase):
    """Alerts reuse the payday fixtures; the morning after payday is 21:00 UTC on 10 Nov."""

    setUp = PaydayEmailTests.setUp
    tearDown = PaydayEmailTests.tearDown
    add_user = PaydayEmailTests.add_user
    sent_at = PaydayEmailTests.sent_at
    MORNING_AFTER = datetime(2026, 11, 10, 21, 0)

    def add_trial(self, name, ends):
        self.db.add(Subscription(
            user_id="owner", name=name, category=Category.streaming, amount=15.99, currency="AUD",
            cycle=BillingCycle.monthly, interval_unit="month", interval_count=1,
            next_due=ends, trial_ends_at=ends,
        ))
        self.db.commit()

    def subjects(self):
        return [call.kwargs["json"]["subject"] for call in self.send.call_args_list]

    def test_bills_that_wont_fit_alert_once_the_morning_after_payday(self):
        self.add_user(pay_amount=Decimal("60.00"))

        self.assertEqual(self.sent_at(PAYDAY_MORNING), 1)  # the payday email only
        self.assertEqual(self.sent_at(self.MORNING_AFTER), 1)
        self.assertEqual(self.sent_at(self.MORNING_AFTER.replace(hour=23)), 0)
        self.assertEqual(
            self.subjects()[-1], "Heads up: bills before Tue 24 Nov are A$25.00 more than you have",
        )

    def test_a_trial_ending_within_three_days_alerts_once(self):
        self.add_user()
        self.add_trial("Stan", datetime(2026, 11, 13, 12, 0))

        self.assertEqual(self.sent_at(datetime(2026, 11, 8, 21, 0)), 0)  # 9 Nov: four days out
        self.assertEqual(self.sent_at(self.MORNING_AFTER), 1)
        self.assertEqual(self.sent_at(self.MORNING_AFTER + timedelta(days=1)), 0)
        self.assertEqual(self.subjects(), ["Stan: offer ends Fri 13 Nov"])
        self.assertIn("After that it's A$15.99", self.send.call_args.kwargs["json"]["text"])

    def test_a_name_with_a_link_reaches_the_email_without_it(self):
        self.add_user()
        self.add_trial("Locked! Verify at https://evil.example/x or evil.example", datetime(2026, 11, 13, 12, 0))

        self.sent_at(self.MORNING_AFTER)

        payload = self.send.call_args.kwargs["json"]
        for part in (payload["subject"], payload["text"]):
            self.assertNotIn("evil.example", part)
            self.assertNotIn("https://evil", part)
        self.assertIn("Locked! Verify at or evil example", payload["subject"])

    def test_no_more_than_two_alerts_per_pay_cycle(self):
        self.add_user(pay_amount=Decimal("60.00"))
        for name in ("Stan", "Binge", "Kayo"):
            self.add_trial(name, datetime(2026, 11, 12, 12, 0))

        self.sent_at(self.MORNING_AFTER)
        self.sent_at(self.MORNING_AFTER + timedelta(days=1))

        self.assertEqual(len(self.subjects()), 2)

    def test_alerts_follow_the_payday_opt_out(self):
        self.add_user(payday=False, pay_amount=Decimal("60.00"))

        self.assertEqual(self.sent_at(self.MORNING_AFTER), 0)


class PaydayOptInTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        for target in ("resend_api_key", "reminder_email_from"):
            patcher = patch(f"app.routers.email_reminders.settings.{target}", "configured")
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def request(self, email="owner@example.com", **claims):
        token = jwt.encode({"email": email, **claims}, "unused-secret-of-sufficient-length-32b")
        return SimpleNamespace(headers={"authorization": f"Bearer {token}"})

    def test_anonymous_or_unverified_accounts_cannot_opt_in(self):
        for claims in ({"is_anonymous": True}, {"user_metadata": {"email_verified": False}}):
            with self.subTest(claims=claims), self.assertRaises(HTTPException) as caught:
                set_email_preferences(EmailOptIn(payday=True), self.request(**claims), user_id="owner", db=self.db)
            self.assertEqual(caught.exception.status_code, 403)
        self.assertIsNone(self.db.get(EmailPreference, "owner"))

    def test_a_verified_account_can_opt_in(self):
        request = self.request(is_anonymous=False, user_metadata={"email_verified": True})

        result = set_email_preferences(EmailOptIn(payday=True), request, user_id="owner", db=self.db)

        self.assertTrue(result["payday"])

    def test_payday_turns_on_without_payment_reminders(self):
        result = set_email_preferences(EmailOptIn(payday=True), self.request(), user_id="owner", db=self.db)

        self.assertEqual((result["payday"], result["enabled"], result["email"]), (True, False, "owner@example.com"))

    def test_each_switch_leaves_the_other_alone(self):
        set_email_preferences(EmailOptIn(enabled=True, payday=True), self.request(), user_id="owner", db=self.db)

        set_email_preferences(EmailOptIn(payday=False), self.request(), user_id="owner", db=self.db)

        result = get_email_preferences(user_id="owner", db=self.db)
        self.assertEqual((result["enabled"], result["payday"]), (True, False))

    def test_a_request_must_change_something(self):
        with self.assertRaises(ValidationError):
            EmailOptIn()

    def test_demo_accounts_cannot_opt_in(self):
        with self.assertRaises(HTTPException) as caught:
            set_email_preferences(EmailOptIn(payday=True), self.request(), user_id="demo_abc", db=self.db)
        self.assertEqual(caught.exception.status_code, 403)


class EmailSafeNameTests(unittest.TestCase):
    def test_links_and_domains_are_removed_or_broken_apart(self):
        self.assertEqual(email_safe_name("Go to http://a.example/x now"), "Go to now")
        self.assertEqual(email_safe_name("www.evil.example/login"), "A payment")
        self.assertEqual(email_safe_name("Amazon.com Prime"), "Amazon com Prime")

    def test_plain_names_are_unchanged_and_long_ones_are_cut(self):
        self.assertEqual(email_safe_name("Netflix Premium 4K"), "Netflix Premium 4K")
        self.assertEqual(email_safe_name("Rent\n\nPay now"), "Rent Pay now")
        self.assertEqual(len(email_safe_name("x" * 200)), 60)


if __name__ == "__main__":
    unittest.main()
