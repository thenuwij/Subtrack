import base64
import hashlib
import hmac
import json
import os
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base, get_db  # noqa: E402
from app.gmail.analyzer import AnalysisOutcome  # noqa: E402
from app.models import Bill, DetectedSubscription, GmailReceipt, InboundAddress, InboundMessage  # noqa: E402
from app.routers import inbound  # noqa: E402

SECRET = "inbound-test-secret"
TOKEN = "k3x9token"
GMAIL = "thenuja.sample@gmail.com"
FORWARDER = "thenuja.sample+caf_=k3x9token=pocketday.app@gmail.com"
GMAIL_PASS = (
    "mx.cloudflare.net; dkim=pass header.d=netflix.com header.s=s1; "
    "spf=pass (mx.cloudflare.net: domain of sender designates 1.2.3.4) smtp.mailfrom=" + FORWARDER
)
GOOGLE_PASS = "mx.cloudflare.net; dkim=pass header.d=google.com; spf=pass smtp.mailfrom=forwarding-noreply@google.com"


def email(subject, body, *, sender="Netflix <info@netflix.com>", auth=GMAIL_PASS, message_id="<abc@netflix.com>"):
    lines = [
        f"Authentication-Results: {auth}",
        f"From: {sender}",
        f"To: {GMAIL}",
        f"Subject: {subject}",
        "Date: Tue, 10 Nov 2026 09:00:00 +1100",
        f"Message-ID: {message_id}",
        "Content-Type: text/plain; charset=utf-8",
        "",
        body,
    ]
    return "\r\n".join(lines).encode()


RECEIPT = email("Your Netflix receipt", "Premium plan for thenuja family\nTotal: A$25.99\nThanks for your payment.")


class InboundEmailTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        db = self.Session()
        db.add(InboundAddress(user_id="owner", token=TOKEN, gmail_address=GMAIL, status="pending"))
        db.commit()
        db.close()

        app = FastAPI()
        app.include_router(inbound.router)

        def override_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)
        self.analyzed = []

        def fake_analyze(candidates, on_batch=None, **_kwargs):
            self.analyzed.extend(candidates)
            if on_batch:
                on_batch([])
            return AnalysisOutcome([], 1, 1, 1, 0, False, False)

        patches = [
            patch.object(inbound.settings, "inbound_email_secret", SECRET),
            patch.object(inbound.settings, "inbound_email_domain", "pocketday.app"),
            patch.object(inbound, "SessionLocal", self.Session),
            patch.object(inbound._executor, "submit", lambda fn, *args: fn(*args)),
            patch("app.gmail.analyzer.analyze_bounded", fake_analyze),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def tearDown(self):
        self.engine.dispose()

    def post(self, raw, *, envelope_from=FORWARDER, timestamp=None, secret=SECRET, to=f"{TOKEN}@pocketday.app"):
        body = json.dumps({
            "envelope_from": envelope_from,
            "envelope_to": to,
            "raw": base64.b64encode(raw).decode(),
        }).encode()
        timestamp = str(int(time.time()) if timestamp is None else timestamp)
        signature = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
        return self.client.post(
            "/inbound/email",
            content=body,
            headers={"X-Inbound-Timestamp": timestamp, "X-Inbound-Signature": signature},
        )

    def rows(self, model):
        db = self.Session()
        try:
            return db.query(model).all()
        finally:
            db.close()

    def address(self):
        db = self.Session()
        try:
            return db.get(InboundAddress, "owner")
        finally:
            db.close()

    def test_bad_signature_is_unauthorised_and_stores_nothing(self):
        response = self.post(RECEIPT, secret="wrong-secret")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.rows(InboundMessage), [])

    def test_stale_timestamp_is_unauthorised(self):
        response = self.post(RECEIPT, timestamp=int(time.time()) - 301)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.rows(InboundMessage), [])

    def test_endpoint_is_disabled_without_a_secret(self):
        with patch.object(inbound.settings, "inbound_email_secret", ""):
            response = self.post(RECEIPT)

        self.assertEqual(response.status_code, 404)

    def test_unknown_token_is_rejected_without_storing_anything(self):
        response = self.post(RECEIPT, to="nobody@pocketday.app")

        self.assertEqual(response.json(), {"outcome": "rejected"})
        self.assertEqual(self.rows(InboundMessage), [])

    def test_spoofed_sender_is_rejected(self):
        response = self.post(RECEIPT, envelope_from="attacker+caf_=k3x9token=pocketday.app@gmail.com")

        self.assertEqual(response.json(), {"outcome": "rejected"})
        self.assertEqual(self.rows(InboundMessage), [])
        self.assertEqual(self.rows(GmailReceipt), [])

    def test_forged_authentication_results_are_rejected(self):
        forged = email("Your Netflix receipt", "Total: A$25.99", auth="evil.example; spf=pass smtp.mailfrom=x@gmail.com")

        response = self.post(forged)

        self.assertEqual(response.json(), {"outcome": "rejected"})

    def test_lookalike_domain_does_not_pass_authentication(self):
        lookalike = email("Your Netflix receipt", "Total: A$25.99", auth="mx.cloudflare.net; spf=pass smtp.mailfrom=x@evilgmail.com")

        response = self.post(lookalike)

        self.assertEqual(response.json(), {"outcome": "rejected"})

    def test_one_time_code_is_filtered_and_nothing_saved(self):
        otp = email("Your verification code", "Your one-time code is 482913. Total: A$1.00 paid.")

        response = self.post(otp)

        self.assertEqual(response.json(), {"outcome": "filtered"})
        self.assertEqual([row.outcome for row in self.rows(InboundMessage)], ["filtered"])
        self.assertEqual(self.rows(GmailReceipt), [])
        self.assertEqual(self.rows(Bill), [])
        self.assertEqual(self.rows(DetectedSubscription), [])
        self.assertEqual(self.analyzed, [])

    def test_password_reset_is_filtered(self):
        reset = email("Reset your password", "Click below to reset your password.")

        self.assertEqual(self.post(reset).json(), {"outcome": "filtered"})

    def test_forwarding_confirmation_stores_code_and_gmail_address(self):
        db = self.Session()
        db.get(InboundAddress, "owner").gmail_address = None
        db.commit()
        db.close()
        confirmation = email(
            "(#123456789) Gmail Forwarding Confirmation - Receive Mail from New.Person@gmail.com",
            "New.Person@gmail.com has requested to automatically forward mail to your email address.",
            sender="Gmail Team <forwarding-noreply@google.com>",
            auth=GOOGLE_PASS,
            message_id="<confirm@google.com>",
        )

        response = self.post(confirmation, envelope_from="forwarding-noreply@google.com")

        self.assertEqual(response.json(), {"outcome": "confirmation"})
        address = self.address()
        self.assertEqual(address.confirmation_code, "123456789")
        self.assertEqual(address.gmail_address, "new.person@gmail.com")
        self.assertIsNotNone(address.confirmation_received_at)
        self.assertEqual(address.status, "pending")

    def test_duplicate_email_is_processed_once(self):
        first = self.post(RECEIPT)
        second = self.post(RECEIPT)

        self.assertEqual(first.json(), {"outcome": "accepted"})
        self.assertEqual(second.json(), {"outcome": "duplicate"})
        self.assertEqual(len(self.rows(InboundMessage)), 1)
        self.assertEqual(len(self.rows(GmailReceipt)), 1)
        self.assertEqual(len(self.analyzed), 1)

    def test_receipt_is_saved_and_analysed_with_a_redacted_candidate(self):
        db = self.Session()
        db.get(InboundAddress, "owner").confirmation_code = "123456789"
        db.commit()
        db.close()

        response = self.post(RECEIPT)

        self.assertEqual(response.json(), {"outcome": "accepted"})
        [receipt] = self.rows(GmailReceipt)
        [message] = self.rows(InboundMessage)
        self.assertEqual((receipt.intermediary, float(receipt.amount), receipt.currency), ("netflix.com", 25.99, "AUD"))
        self.assertEqual(receipt.gmail_message_id, message.message_hash)
        self.assertEqual(message.outcome, "accepted")
        [candidate] = self.analyzed
        self.assertNotIn("thenuja", f"{candidate.subject} {candidate.excerpt}".lower())
        self.assertIn("[name]", candidate.excerpt)
        address = self.address()
        self.assertEqual(address.status, "active")
        self.assertIsNone(address.confirmation_code)

    def test_inbound_messages_hold_no_email_text(self):
        self.post(RECEIPT)

        [message] = self.rows(InboundMessage)
        stored = " ".join(str(getattr(message, column.name)) for column in InboundMessage.__table__.columns)
        for text in ("Netflix", "netflix.com", "receipt", "25.99", "Premium", GMAIL):
            self.assertNotIn(text, stored)
        self.assertEqual(len(message.message_hash), 64)


if __name__ == "__main__":
    unittest.main()
