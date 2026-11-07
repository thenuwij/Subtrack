import base64
import os
import unittest
from datetime import date, datetime

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.gmail.analyzer import DetectedSubscription as Found  # noqa: E402
from app.gmail.bills import read_bill  # noqa: E402
from app.gmail.scanner import ReceiptCandidate, _extract_body_text  # noqa: E402
from app.gmail.terms import next_weekday_rule, read_terms  # noqa: E402
from app.routers.gmail import _apply_stated_terms, _terms_by_domain  # noqa: E402


class TermsTests(unittest.TestCase):
    def test_google_play_intro_price(self):
        terms = read_terms(
            "You will be automatically charged $2.99/month for 3 months, then $32.99/month starting Jan 30, 2027",
            date(2026, 11, 1),
        )
        self.assertEqual((terms.intro_amount, terms.full_amount, terms.intro_ends_on), (2.99, 32.99, date(2027, 1, 30)))

    def test_intro_without_a_stated_end_counts_the_months(self):
        terms = read_terms("$1 per month for 2 months, then $10 per month", date(2026, 11, 15))
        self.assertEqual(terms.intro_ends_on, date(2027, 1, 15))

    def test_first_thursday_of_each_month(self):
        terms = read_terms("NEXT DIRECT DEBIT DATE: First Thursday of each month", date(2026, 11, 6))
        self.assertEqual(terms.next_due, date(2026, 12, 3))

    def test_last_friday_rule(self):
        self.assertEqual(next_weekday_rule(date(2026, 11, 1), 4, -1), date(2026, 11, 27))

    def test_no_terms(self):
        terms = read_terms("Thanks for your payment", date(2026, 11, 6))
        self.assertIsNone(terms.intro_amount)
        self.assertIsNone(terms.next_due)


class StatedTermsOnFindingsTests(unittest.TestCase):
    def candidate(self, **fields):
        return ReceiptCandidate("m", "google.com", "Google Play", "Receipt", "2026-11-01", 2.99, "AUD", "high", **fields)

    def finding(self, **fields):
        values = dict(sender_domain="google.com", merchant="Google AI Pro", product_key="google-ai-pro",
                      cadence_confidence="unknown", amount=2.99, currency="AUD", cancelled=False,
                      category="cloud", confidence="medium", charge_count=1)
        return Found(**{**values, **fields})

    def test_intro_price_is_applied_to_the_finding(self):
        found = self.finding()
        terms = _terms_by_domain([self.candidate(intro_amount=2.99, full_amount=32.99, intro_ends_on="2099-01-30")])
        _apply_stated_terms([found], terms)
        self.assertEqual((found.intro_amount, found.amount), (2.99, 32.99))
        self.assertEqual(found.trial_ends_at.date(), date(2099, 1, 30))

    def test_stated_debit_day_sets_date_and_monthly(self):
        found = self.finding(sender_domain="slsa.com.au")
        candidate = ReceiptCandidate("m", "slsa.com.au", "SLSA", "Tickets", "2026-11-06", 5.0, "AUD", "high",
                                     stated_next_due="2026-12-03")
        _apply_stated_terms([found], _terms_by_domain([candidate]))
        self.assertEqual(found.next_due, datetime(2026, 12, 3, 12))
        self.assertEqual((found.interval_unit, found.interval_count), ("month", 1))


class EmailBodyTests(unittest.TestCase):
    def part(self, mime, text):
        return {"mimeType": mime, "body": {"data": base64.urlsafe_b64encode(text.encode()).decode()}}

    def test_html_used_when_plain_text_has_no_prices(self):
        payload = {"mimeType": "multipart/alternative", "parts": [
            self.part("text/plain", "Tax Invoice App Store"),
            self.part("text/html", "<p>iCloud+ 2TB</p><p>$14.99</p>"),
        ]}
        self.assertIn("$14.99", _extract_body_text(payload))

    def test_plain_text_kept_when_it_has_prices(self):
        payload = {"mimeType": "multipart/alternative", "parts": [
            self.part("text/plain", "Amount paid $9.99"),
            self.part("text/html", "<p>$9.99</p>"),
        ]}
        self.assertEqual(_extract_body_text(payload), "Amount paid $9.99")


class BillReaderTests(unittest.TestCase):
    def test_vodafone_balance_and_due(self):
        bill = read_bill("Your Vodafone email bill for 17-09-2026 to 16-10-2026",
                         "| Total balance due |\n| $140.59DR |\n| Due 03 Nov 2026 |")
        self.assertEqual((bill.amount_due, bill.due_on), (140.59, date(2026, 11, 3)))

    def test_water_invoice(self):
        bill = read_bill("New invoice due for 90/2-6 Willis St",
                         "The amount owing is $118.55 and is due for payment on 6/11/2026.")
        self.assertEqual((bill.amount_due, bill.due_on), (118.55, date(2026, 11, 6)))

    def test_late_fee_only_when_stated(self):
        bill = read_bill("Your bill", "Amount due $68.00 Due 03 Nov 2026 Late payment fee $10.00")
        self.assertEqual(bill.late_fee, 10.0)
        self.assertIsNone(read_bill("Your bill", "Amount due $68.00").late_fee)

    def test_origin_pdf_due_date(self):
        bill = read_bill("Your Origin electricity bill",
                         "Amount due\n$149.77\nDue immediately\n$150.06\nNew charges due 28 Oct 2026\n")
        self.assertEqual(bill.due_on, date(2026, 10, 28))

    def test_receipts_are_not_bills(self):
        self.assertIsNone(read_bill("Receipt for your payment to Origin Energy", "Paid $150.06"))


if __name__ == "__main__":
    unittest.main()
