import os
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import AiCallTrace  # noqa: E402
from app.services import ai_tracing  # noqa: E402
from app.services.ai_tracing import (  # noqa: E402
    AiBudgetExceeded,
    call_cost,
    record_call,
    traced_call,
    usage_summary,
)

MODEL = "claude-haiku-4-5"
NOW = datetime(2026, 11, 6, 9, 0)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fake_response(**usage):
    counts = {
        "input_tokens": 1_000,
        "output_tokens": 200,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        **usage,
    }
    return SimpleNamespace(stop_reason="end_turn", usage=SimpleNamespace(**counts))


class AiTracingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        patcher = patch("app.services.ai_tracing.SessionLocal", self.Session)
        patcher.start()
        self.addCleanup(patcher.stop)
        ai_tracing._spend_cache.clear()
        self.addCleanup(ai_tracing._spend_cache.clear)

    def tearDown(self):
        self.engine.dispose()

    def traces(self):
        with self.Session() as db:
            return db.query(AiCallTrace).all()

    def test_cost_uses_each_token_type_and_web_searches(self):
        cost = call_cost(
            MODEL,
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_read_tokens=1_000_000,
            cache_write_tokens=1_000_000,
            web_searches=2,
        )
        self.assertEqual(cost, Decimal("7.37"))

    def test_unknown_model_costs_nothing_rather_than_guessing(self):
        cost = call_cost(
            "some-future-model", input_tokens=500, output_tokens=500,
            cache_read_tokens=0, cache_write_tokens=0, web_searches=0,
        )
        self.assertEqual(cost, Decimal(0))

    def test_traced_call_records_tokens_latency_and_cost(self):
        call = Mock(return_value=fake_response(cache_read_input_tokens=4_000))

        response = traced_call("gmail_analysis", call, model=MODEL, max_tokens=10)

        self.assertIs(response, call.return_value)
        call.assert_called_once_with(model=MODEL, max_tokens=10)
        [trace] = self.traces()
        self.assertEqual(trace.feature, "gmail_analysis")
        self.assertEqual((trace.input_tokens, trace.output_tokens), (1_000, 200))
        self.assertEqual(trace.cache_read_tokens, 4_000)
        self.assertEqual(trace.cost_usd, Decimal("0.002400"))
        self.assertEqual(trace.stop_reason, "end_turn")
        self.assertGreaterEqual(trace.latency_ms, 0)
        self.assertIsNone(trace.error_code)

    def test_traced_call_records_failures_and_reraises(self):
        call = Mock(side_effect=TimeoutError("slow"))

        with self.assertRaises(TimeoutError):
            traced_call("duplicate_check", call, model=MODEL)

        [trace] = self.traces()
        self.assertEqual(trace.error_code, "TimeoutError")
        self.assertEqual(trace.cost_usd, Decimal(0))

    def test_recording_never_fails_the_measured_call(self):
        broken = Mock()
        broken.return_value.commit.side_effect = OperationalError("insert", {}, Exception())
        with patch("app.services.ai_tracing.SessionLocal", broken):
            record_call("assistant", MODEL, fake_response(), 10)
        broken.return_value.rollback.assert_called_once()
        broken.return_value.close.assert_called_once()

    def test_unexpected_usage_shapes_are_recorded_as_zero(self):
        record_call("assistant", MODEL, Mock(), 10)

        [trace] = self.traces()
        self.assertEqual(trace.input_tokens, 0)
        self.assertIsNone(trace.stop_reason)

    def test_summary_reports_percentiles_errors_and_cost_per_request(self):
        first_run, second_run = uuid4(), uuid4()
        rows = [
            ("assistant", first_run, 100, 50, None, "0.002"),
            ("assistant", first_run, 300, None, None, "0.004"),
            ("assistant", second_run, 200, None, "APIError", "0"),
            ("gmail_analysis", None, 1_000, None, None, "0.010"),
            ("gmail_analysis", None, 3_000, None, None, "0.030"),
        ]
        with self.Session() as db:
            for feature, run_id, latency, tool_ms, error, cost in rows:
                db.add(AiCallTrace(
                    feature=feature, model=MODEL, run_id=run_id, latency_ms=latency,
                    tool_ms=tool_ms, error_code=error, cost_usd=Decimal(cost),
                    input_tokens=0, output_tokens=0, cache_read_tokens=0,
                    cache_write_tokens=0, web_searches=0, created_at=NOW,
                ))
            db.add(AiCallTrace(
                feature="assistant", model=MODEL, latency_ms=9_999, cost_usd=Decimal(1),
                input_tokens=0, output_tokens=0, cache_read_tokens=0,
                cache_write_tokens=0, web_searches=0, created_at=NOW - timedelta(days=30),
            ))
            db.commit()

            summary = usage_summary(db, NOW - timedelta(days=7))

        assistant = summary["assistant"]
        self.assertEqual(assistant["calls"], 3)
        self.assertAlmostEqual(assistant["error_rate"], 1 / 3)
        self.assertEqual((assistant["p50_ms"], assistant["p95_ms"]), (200, 300))
        self.assertEqual(assistant["requests"], 2)
        self.assertEqual(assistant["request_p95_ms"], 450)
        self.assertEqual(assistant["cost_per_request_usd"], Decimal("0.003"))
        gmail = summary["gmail_analysis"]
        self.assertEqual(gmail["cost_usd"], Decimal("0.040"))
        self.assertNotIn("requests", gmail)


    def add_spend(self, cost, created_at=None):
        with self.Session() as db:
            db.add(AiCallTrace(
                feature="assistant", model=MODEL, latency_ms=1, cost_usd=Decimal(cost),
                created_at=created_at or utcnow(),
            ))
            db.commit()

    def test_ai_calls_stop_once_todays_spend_reaches_the_limit(self):
        self.add_spend("19.50")
        self.add_spend("50.00", created_at=utcnow() - timedelta(days=2))
        call = Mock(return_value=fake_response())
        with patch.object(settings, "ai_daily_cost_limit_usd", 20.0):
            traced_call("bill_parse", call, model=MODEL)
            self.add_spend("0.50")
            ai_tracing._spend_cache.clear()
            with self.assertRaises(AiBudgetExceeded) as caught:
                traced_call("bill_parse", call, model=MODEL)

        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(call.call_count, 1)

    def test_a_zero_limit_disables_the_breaker(self):
        self.add_spend("500.00")
        call = Mock(return_value=fake_response())
        with patch.object(settings, "ai_daily_cost_limit_usd", 0.0):
            traced_call("bill_parse", call, model=MODEL)
        call.assert_called_once()

    def test_an_unreadable_spend_leaves_ai_on(self):
        broken = Mock()
        broken.return_value.query.side_effect = OperationalError("select", {}, Exception())
        with patch("app.services.ai_tracing.SessionLocal", broken):
            ai_tracing.require_ai_budget()


if __name__ == "__main__":
    unittest.main()
