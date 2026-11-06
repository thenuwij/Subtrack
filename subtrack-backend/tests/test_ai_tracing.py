import os
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import AiCallTrace  # noqa: E402
from app.services.ai_tracing import (  # noqa: E402
    call_cost,
    record_call,
    traced_call,
)

MODEL = "claude-haiku-4-5"


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


if __name__ == "__main__":
    unittest.main()
