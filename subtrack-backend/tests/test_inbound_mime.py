import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.gmail import mime  # noqa: E402

CLOUDFLARE_PASS = "mx.cloudflare.net; spf=pass smtp.mailfrom=someone+caf_=x=pocketday.app@gmail.com"


def raw_email(subject: str, body: str, *, sender: str = "Netflix <info@netflix.com>", headers: tuple[str, ...] = ()) -> bytes:
    lines = [
        *headers,
        f"From: {sender}",
        f"Subject: {subject}",
        "Date: Tue, 10 Nov 2026 15:00:00 +1100",
        "Message-ID: <abc@netflix.com>",
        "Content-Type: text/plain; charset=utf-8",
        "",
        body,
    ]
    return "\r\n".join(lines).encode()


class InboundMimeTests(unittest.TestCase):
    def test_receipt_becomes_a_candidate_with_amount_and_date(self):
        message = mime.parse_message(raw_email("Your Netflix receipt", "Premium plan\nTotal: A$25.99"))
        candidate = mime.to_candidate(message, "hash-1", mime.body_text(message))
        self.assertEqual(candidate.message_id, "hash-1")
        self.assertEqual(candidate.sender_domain, "netflix.com")
        self.assertEqual((candidate.amount, candidate.currency), (25.99, "AUD"))
        self.assertEqual(candidate.date, "2026-11-10")

    def test_message_hash_differs_per_user(self):
        raw = raw_email("Receipt", "Total: $5.00")
        message = mime.parse_message(raw)
        self.assertNotEqual(mime.message_hash("user-a", message, raw), mime.message_hash("user-b", message, raw))
        self.assertEqual(len(mime.message_hash("user-a", message, raw)), 64)

    def test_sensitive_emails_are_detected(self):
        self.assertTrue(mime.is_sensitive("Your verification code", "Use 123456 to sign in"))
        self.assertTrue(mime.is_sensitive("Reset your password", ""))
        self.assertFalse(mime.is_sensitive("Your Spotify receipt", "Total: $13.99"))

    def test_forwarding_confirmation_is_read_only_from_google(self):
        subject = "(#123456789) Gmail Forwarding Confirmation - Receive Mail from Someone@gmail.com"
        real = mime.parse_message(raw_email(subject, "", sender="Gmail Team <forwarding-noreply@google.com>"))
        fake = mime.parse_message(raw_email(subject, "", sender="attacker@example.com"))
        self.assertEqual(mime.forwarding_confirmation(real), ("someone@gmail.com", "123456789", None))
        self.assertIsNone(mime.forwarding_confirmation(fake))

    def test_forwarding_confirmation_reads_the_confirm_link_when_there_is_no_code(self):
        subject = "(Gmail Forwarding Confirmation - Receive Mail from Someone@gmail.com"
        body = (
            "please click the link below to confirm the request:\n\n"
            "https://mail.google.com/mail/vf-%5BAbC123%5D-XyZ_789\n\n"
            "To cancel, click: https://mail.google.com/mail/uf-%5BAbC123%5D-XyZ_789\n"
        )
        google = "Gmail Team <forwarding-noreply@google.com>"
        with_link = mime.parse_message(raw_email(subject, body, sender=google))
        without_link = mime.parse_message(raw_email(subject, "no link here", sender=google))
        self.assertEqual(
            mime.forwarding_confirmation(with_link),
            ("someone@gmail.com", None, "https://mail.google.com/mail/vf-%5BAbC123%5D-XyZ_789"),
        )
        self.assertIsNone(mime.forwarding_confirmation(without_link))

    def test_only_cloudflares_topmost_authentication_header_counts(self):
        trusted = mime.parse_message(raw_email("x", "", headers=(f"Authentication-Results: {CLOUDFLARE_PASS}",)))
        forged_below = mime.parse_message(raw_email("x", "", headers=(
            "Authentication-Results: mx.cloudflare.net; spf=fail smtp.mailfrom=evil.example",
            f"Authentication-Results: {CLOUDFLARE_PASS}",
        )))
        self.assertTrue(mime.passes_authentication(trusted, {"gmail.com"}))
        self.assertFalse(mime.passes_authentication(forged_below, {"gmail.com"}))
        self.assertFalse(mime.passes_authentication(trusted, {"google.com"}))

    def test_a_replayed_gmail_dkim_signature_is_not_enough(self):
        dkim_only = mime.parse_message(raw_email("x", "", headers=(
            "Authentication-Results: mx.cloudflare.net; dkim=pass header.d=gmail.com; spf=fail smtp.mailfrom=evil.example",
        )))
        self.assertFalse(mime.passes_authentication(dkim_only, {"gmail.com"}))
