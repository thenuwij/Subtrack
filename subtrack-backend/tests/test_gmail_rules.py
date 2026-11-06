import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.gmail.analyzer import analyze_bounded  # noqa: E402
from app.gmail.rules import detect  # noqa: E402
from app.gmail.scanner import ReceiptCandidate  # noqa: E402


def receipt(domain, date, amount, subject="Your receipt", excerpt="Thanks for your payment.",
            merchant=None, currency="AUD"):
    return ReceiptCandidate(
        message_id=f"{domain}-{date}-{amount}",
        sender_domain=domain,
        merchant=merchant or domain.split(".")[0].title(),
        subject=subject,
        date=date,
        amount=amount,
        currency=currency,
        confidence="high",
        excerpt=excerpt,
    )


class RulesCatchClearPatterns(unittest.TestCase):
    def test_monthly_streaming_with_known_name(self):
        found = detect("netflix.com", [
            receipt("netflix.com", "2026-08-12", 20.99),
            receipt("netflix.com", "2026-09-12", 20.99),
            receipt("netflix.com", "2026-10-12", 20.99),
        ])
        self.assertEqual((found.merchant, found.category), ("Netflix", "streaming"))
        self.assertEqual((found.interval_unit, found.interval_count), ("month", 1))
        self.assertEqual((found.confidence, found.cadence_confidence), ("high", "high"))
        self.assertEqual(found.amount, 20.99)
        self.assertEqual(found.charge_count, 3)

    def test_fortnightly_gym(self):
        dates = ["2026-08-07", "2026-08-21", "2026-09-04", "2026-09-18"]
        found = detect("anytimefitness.com.au", [receipt("anytimefitness.com.au", d, 24.95) for d in dates])
        self.assertEqual((found.interval_unit, found.interval_count), ("week", 2))
        self.assertEqual(found.category, "fitness")

    def test_month_end_billing_across_february(self):
        dates = ["2027-01-31", "2027-02-28", "2027-03-31"]
        found = detect("vodafone.com.au", [receipt("vodafone.com.au", d, 58.0) for d in dates])
        self.assertEqual((found.interval_unit, found.interval_count), ("month", 1))

    def test_two_charges_is_only_medium_confidence(self):
        found = detect("openai.com", [
            receipt("openai.com", "2026-09-03", 30.0),
            receipt("openai.com", "2026-10-03", 30.0),
        ])
        self.assertEqual((found.confidence, found.cadence_confidence), ("medium", "medium"))

    def test_invoice_and_receipt_on_one_day_count_once(self):
        found = detect("spotify.com", [
            receipt("spotify.com", "2026-08-01", 13.99, subject="Your invoice"),
            receipt("spotify.com", "2026-08-01", 13.99),
            receipt("spotify.com", "2026-09-01", 13.99),
            receipt("spotify.com", "2026-10-01", 13.99),
        ])
        self.assertEqual(found.charge_count, 3)

    def test_unknown_sender_uses_its_own_name(self):
        found = detect("smallgym.com.au", [
            receipt("smallgym.com.au", "2026-08-01", 40.0, merchant="Small Gym"),
            receipt("smallgym.com.au", "2026-09-01", 40.0, merchant="Small Gym"),
            receipt("smallgym.com.au", "2026-10-01", 40.0, merchant="Small Gym"),
        ])
        self.assertEqual((found.merchant, found.category, found.product_key), ("Small Gym", "other", "small-gym"))


class RulesLeaveUnclearCasesToTheAI(unittest.TestCase):
    def test_multi_product_sender(self):
        emails = [receipt("apple.com", d, 14.99) for d in ["2026-08-05", "2026-09-05", "2026-10-05"]]
        self.assertIsNone(detect("apple.com", emails))

    def test_trial_wording(self):
        emails = [
            receipt("stan.com.au", "2026-09-01", 12.0, excerpt="Your free trial ends soon"),
            receipt("stan.com.au", "2026-10-01", 12.0),
        ]
        self.assertIsNone(detect("stan.com.au", emails))

    def test_cancellation_or_refund(self):
        emails = [
            receipt("binge.com.au", "2026-09-01", 18.0),
            receipt("binge.com.au", "2026-10-01", 18.0, subject="Your subscription was cancelled"),
        ]
        self.assertIsNone(detect("binge.com.au", emails))

    def test_amounts_that_vary(self):
        emails = [receipt("agl.com.au", d, a) for d, a in [("2026-08-10", 142.0), ("2026-09-10", 98.5), ("2026-10-10", 120.0)]]
        self.assertIsNone(detect("agl.com.au", emails))

    def test_irregular_gaps(self):
        emails = [receipt("shop.com", d, 25.0) for d in ["2026-08-01", "2026-08-19", "2026-10-02"]]
        self.assertIsNone(detect("shop.com", emails))

    def test_single_receipt(self):
        self.assertIsNone(detect("netflix.com", [receipt("netflix.com", "2026-10-12", 20.99)]))

    def test_mixed_currencies(self):
        emails = [
            receipt("github.com", "2026-09-01", 4.0, currency="USD"),
            receipt("github.com", "2026-10-01", 4.0, currency="AUD"),
        ]
        self.assertIsNone(detect("github.com", emails))


class AnalyzerUsesRulesFirst(unittest.TestCase):
    def test_clear_senders_skip_the_ai_and_unclear_ones_still_reach_it(self):
        candidates = [
            *(receipt("netflix.com", d, 20.99) for d in ["2026-08-12", "2026-09-12", "2026-10-12"]),
            *(receipt("apple.com", d, 14.99) for d in ["2026-08-05", "2026-09-05"]),
        ]
        batches = []
        with patch("app.gmail.analyzer._analyze_chunk", return_value=[]) as ai:
            outcome = analyze_bounded(candidates, on_batch=batches.append)

        ai_domains = [domain for call in ai.call_args_list for domain in call.args[0]]
        self.assertEqual(ai_domains, ["apple.com"])
        self.assertEqual([f.merchant for f in outcome.subscriptions], ["Netflix"])
        self.assertEqual(batches[0][0].merchant, "Netflix")

    def test_inbox_of_only_clear_senders_makes_no_ai_call(self):
        candidates = [receipt("netflix.com", d, 20.99) for d in ["2026-08-12", "2026-09-12", "2026-10-12"]]
        with patch("app.gmail.analyzer._analyze_chunk") as ai:
            outcome = analyze_bounded(candidates)
        ai.assert_not_called()
        self.assertEqual(len(outcome.subscriptions), 1)
        self.assertFalse(outcome.truncated)


if __name__ == "__main__":
    unittest.main()
