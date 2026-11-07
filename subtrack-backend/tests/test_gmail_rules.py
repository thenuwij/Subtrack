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


class GmailFetchTimeoutTests(unittest.TestCase):
    """A slow Gmail batch is retried; it must not fail the whole scan."""

    def _service(self, outcomes):
        from unittest import mock
        calls = {"n": 0}

        def new_batch(callback):
            batch = mock.Mock()
            added = []
            batch.add.side_effect = lambda request, request_id: added.append(request_id)

            def execute():
                outcome = outcomes[min(calls["n"], len(outcomes) - 1)]
                calls["n"] += 1
                if outcome == "timeout":
                    raise TimeoutError("The read operation timed out")
                for message_id in added:
                    callback(message_id, {"id": message_id}, None)
            batch.execute.side_effect = execute
            return batch

        service = mock.Mock()
        service.new_batch_http_request.side_effect = new_batch
        return service, calls

    def _fetch(self, outcomes):
        from unittest import mock

        import app.gmail.scanner as scanner
        service, calls = self._service(outcomes)
        with mock.patch.object(scanner, "_to_candidate", side_effect=_with_id), \
                mock.patch.object(scanner.time, "sleep"):
            return scanner._fetch_all(service, [f"m{i}" for i in range(3)]), calls

    def test_timeout_is_retried_and_scan_continues(self):
        (candidates, incomplete), calls = self._fetch(["timeout", "ok"])
        self.assertEqual(len(candidates), 3)
        self.assertFalse(incomplete)
        self.assertEqual(calls["n"], 2)

    def test_repeated_timeouts_report_incomplete_instead_of_crashing(self):
        (candidates, incomplete), _ = self._fetch(["timeout"])
        self.assertEqual(candidates, [])
        self.assertTrue(incomplete)


def _with_id(response):
    candidate = receipt("x.com", "2026-10-01", 1.0)
    candidate.message_id = response["id"]
    return candidate


class PaymentProofTests(unittest.TestCase):
    def check(self, subject, excerpt=""):
        from app.routers.gmail import _is_payment_proof
        return _is_payment_proof(receipt("x.com", "2026-10-01", 10.0, subject=subject, excerpt=excerpt))

    def test_receipts_count(self):
        self.assertTrue(self.check("Receipt for your payment to Origin Energy"))
        self.assertTrue(self.check("Debitsuccess Payment Receipt: 15871945"))
        self.assertTrue(self.check("Your tax invoice from Apple."))

    def test_bills_and_notices_do_not(self):
        self.assertFalse(self.check("Your Origin electricity bill"))
        self.assertFalse(self.check("Your Vodafone email bill for 17-09-2026 to 16-10-2026"))
        self.assertFalse(self.check("New invoice due for 90/2-6 Willis St"))
        self.assertFalse(self.check("Your bill is now overdue"))
        self.assertFalse(self.check("Debitsuccess Payment Unsuccessful"))
