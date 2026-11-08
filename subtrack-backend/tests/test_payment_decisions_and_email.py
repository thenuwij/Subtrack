import unittest
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.models import EmailPreference, PaymentDecision, PaymentReminder, ReminderDelivery
from app.routers.subscriptions import PaymentDecisionInput, decide_payment, ways_to_save
from app.services.email_reminders import send_due
from app.services.paid_history import paid_history
from tests import test_paid_history as history_fixtures


class PaymentAndEmailTests(unittest.TestCase):
    def setUp(self):
        self.fixture = history_fixtures.PaidHistoryTests()
        self.fixture.setUp()
        self.db = self.fixture.db
        self.sub = self.fixture.netflix

    def tearDown(self):
        self.fixture.tearDown()

    def test_manual_paid_and_undo(self):
        target = f"payment:{self.sub.id}:2026-10-12"
        self.db.add(PaymentDecision(user_id="owner", target=target, decision="paid"))
        self.db.commit()
        rows = paid_history(self.db, "owner", today=date(2026, 11, 7))["payments"]
        row = next(r for r in rows if r.get("target") == target)
        self.assertEqual((row["status"], row["manual"]), ("confirmed", "paid"))
        decide_payment(PaymentDecisionInput(target=target, decision="undo"), "owner", self.db)
        self.assertEqual(self.db.query(PaymentDecision).count(), 0)

    def test_paid_with_a_different_amount_shows_that_amount(self):
        target = f"payment:{self.sub.id}:2026-10-12"
        decide_payment(PaymentDecisionInput(target=target, decision="paid", amount=9.99), "owner", self.db)
        rows = paid_history(self.db, "owner", today=date(2026, 11, 7))["payments"]
        row = next(r for r in rows if r.get("target") == target)
        self.assertEqual((row["status"], row["amount"], row["paid_amount"]), ("confirmed", 9.99, 9.99))

        decide_payment(PaymentDecisionInput(target=target, decision="paid"), "owner", self.db)
        rows = paid_history(self.db, "owner", today=date(2026, 11, 7))["payments"]
        row = next(r for r in rows if r.get("target") == target)
        self.assertIsNone(row["paid_amount"])
        self.assertEqual(row["amount"], float(self.sub.amount))

    def test_past_payments_keep_the_price_they_had_then(self):
        from app.models import ChangeKind, SubscriptionChange

        self.sub.amount = 9.99
        self.db.add(SubscriptionChange(
            user_id="owner", subscription_id=self.sub.id, name="Netflix", kind=ChangeKind.price_change,
            old_monthly=20.99, new_monthly=9.99, currency=self.sub.currency, changed_at=datetime(2026, 11, 5),
        ))
        self.db.commit()
        rows = paid_history(self.db, "owner", today=date(2026, 11, 20))["payments"]
        by_date = {r["date"]: r["amount"] for r in rows if r["kind"] == "schedule"}
        self.assertEqual(by_date["2026-10-12"], 20.99)
        self.assertEqual(by_date["2026-11-12"], 9.99)

    def test_amount_is_only_accepted_for_paid_payments(self):
        target = f"payment:{self.sub.id}:2026-10-12"
        with self.assertRaises(HTTPException) as error:
            decide_payment(PaymentDecisionInput(target=target, decision="skipped", amount=5), "owner", self.db)
        self.assertEqual(error.exception.status_code, 422)

    def test_later_receipt_wins_without_double_counting_manual_or_skipped(self):
        target = f"payment:{self.sub.id}:2026-10-12"
        self.db.add(PaymentDecision(user_id="owner", target=target, decision="skipped"))
        self.db.commit()
        rows = paid_history(self.db, "owner", today=date(2026, 11, 7))["payments"]
        self.assertEqual(next(r for r in rows if r.get("target") == target)["status"], "skipped")
        self.fixture.receipt("netflix.com", date(2026, 10, 13), 20.99)
        rows = paid_history(self.db, "owner", today=date(2026, 11, 7))["payments"]
        october = [r for r in rows if r["date"].startswith("2026-10")]
        self.assertEqual(len(october), 1)
        self.assertEqual(october[0]["kind"], "receipt")

    def test_cannot_confirm_another_users_occurrence(self):
        with self.assertRaises(HTTPException) as error:
            decide_payment(
                PaymentDecisionInput(target=f"payment:{self.sub.id}:2026-10-12", decision="paid"), "intruder", self.db
            )
        self.assertEqual(error.exception.status_code, 404)

    def prepare_email(self):
        self.db.add(EmailPreference(user_id="owner", email="owner@example.com", enabled=True))
        self.db.add(
            PaymentReminder(
                id=uuid4(), user_id="owner", subscription_id=self.sub.id, kind="renewal", days_before=7, is_active=True
            )
        )
        self.db.commit()

    def test_delivery_deduplicates_and_respects_opt_out(self):
        self.prepare_email()
        send = Mock(return_value=httpx.Response(200, request=httpx.Request("POST", "https://api.resend.com/emails")))
        now = datetime(2026, 11, 8, 10)
        with (
            patch("app.services.email_reminders.settings.resend_api_key", "test"),
            patch("app.services.email_reminders.settings.reminder_email_from", "Subtrack <hello@example.com>"),
        ):
            self.assertEqual(send_due(self.db, now=now, send=send)["sent"], 1)
            self.assertEqual(send_due(self.db, now=now, send=send)["sent"], 0)
            self.assertEqual(send.call_count, 1)
            self.db.get(EmailPreference, "owner").enabled = False
            self.db.commit()
            self.assertEqual(send_due(self.db, now=now + timedelta(days=1), send=send)["sent"], 0)

    def test_failed_delivery_reuses_payload_and_stops_before_idempotency_expires(self):
        self.prepare_email()
        send = Mock(side_effect=httpx.ReadTimeout("timeout"))
        now = datetime(2026, 11, 8, 10)
        with (
            patch("app.services.email_reminders.settings.resend_api_key", "test"),
            patch("app.services.email_reminders.settings.reminder_email_from", "hello@example.com"),
        ):
            self.assertEqual(send_due(self.db, now=now, send=send)["failed"], 1)
            payload = self.db.query(ReminderDelivery).one().payload
            self.sub.name = "Renamed payment"
            self.db.commit()
            send_due(self.db, now=now + timedelta(hours=1), send=send)
            self.assertEqual(send.call_args.kwargs["json"], payload)
            self.assertEqual(send_due(self.db, now=now + timedelta(hours=24), send=send)["expired"], 1)
            self.assertEqual(send.call_count, 2)

    def test_savings_reports_no_price_rises_instead_of_all_changes(self):
        with patch("app.agent.finance.duplicate_payments", return_value={"suggestions": []}):
            result = ways_to_save("owner", self.db)
        self.assertEqual(result["price_rises"], [])
        self.assertEqual(result["late_fees_total"], 0)
