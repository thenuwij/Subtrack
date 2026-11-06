import json
import os
import unittest
from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.agent.tools import TOOL_DEFINITIONS  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import AgentAction  # noqa: E402
from evals.graders import (  # noqa: E402
    ToolCall,
    Transcript,
    grade,
    grade_boundary,
    grade_numbers,
    grade_tools,
)
from evals.harness import load_cases, run_case, seed, utc_now  # noqa: E402

USAGE = SimpleNamespace(
    input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0,
)


class FakeStream:
    def __init__(self, text, final):
        self.text_stream = [text] if text else []
        self.final = final

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.final


def scripted_model(tool_name, tool_input, answer_from_result):
    """Call one tool, then answer using a function of that tool's result."""

    def stream(**kwargs):
        last = kwargs["messages"][-1]
        if last["role"] == "user" and isinstance(last["content"], list):
            result = json.loads(last["content"][0]["content"])
            text = answer_from_result(result)
            return FakeStream(text, SimpleNamespace(stop_reason="end_turn", content=[], usage=USAGE))
        call = SimpleNamespace(type="tool_use", id="tool-1", name=tool_name, input=tool_input)
        return FakeStream("", SimpleNamespace(stop_reason="tool_use", content=[call], usage=USAGE))

    return stream


class EvalHarnessTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        seed(self.db, utc_now())

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_grounded_safe_to_spend_answer_passes_every_grader(self):
        model = scripted_model(
            "get_safe_to_spend", {},
            lambda r: f"You can spend ${r['safe_to_spend']:.2f}, about ${r['per_day']:.2f} a day.",
        )
        case = {"expected_tools": ["get_safe_to_spend"]}

        transcript = run_case(self.db, "How much can I safely spend?", model)

        self.assertIn("$392.01", transcript.answer)
        self.assertTrue(all(g.passed for g in grade(transcript, case)), grade(transcript, case))

    def test_an_invented_amount_fails_the_numbers_grader(self):
        model = scripted_model("get_safe_to_spend", {}, lambda r: "You can spend $450.00.")

        transcript = run_case(self.db, "How much can I safely spend?", model)

        self.assertFalse(grade_numbers(transcript).passed)

    def test_a_proposal_changes_nothing_until_confirmed(self):
        payment = {
            "name": "iCloud", "category": "cloud", "amount": 12, "currency": "AUD",
            "interval_unit": "month", "interval_count": 1,
            "next_due": (utc_now() + timedelta(days=14)).isoformat(),
            "trial_ends_at": None, "recurrence_end_at": None, "status": "active",
            "paused_until": None, "cancellation_effective_at": None,
            "amount_type": "fixed", "spending_type": "optional",
        }
        model = scripted_model(
            "propose_add_recurring_payment", payment, lambda r: "Ready for you to confirm.",
        )

        transcript = run_case(self.db, "Add a $12 monthly iCloud payment.", model)

        self.assertFalse(transcript.data_changed)
        self.assertEqual(self.db.query(AgentAction).one().status, "pending")


class GraderTests(unittest.TestCase):
    def transcript(self, answer, result=None, question="How much?"):
        calls = [ToolCall("get_safe_to_spend", {}, result)] if result is not None else []
        return Transcript(question=question, answer=answer, tool_calls=calls)

    def test_amounts_may_come_from_nested_results_or_the_question(self):
        result = {"commitments": [{"amount": "1234.50"}], "per_day": 43.55}
        answer = "Rent is $1,234.50, you have AUD 43.55 a day, and $60 dinner fits."

        self.assertTrue(grade_numbers(self.transcript(answer, result, "Can I spend $60?")).passed)

    def test_amounts_within_a_cent_are_accepted_and_others_are_named(self):
        grade_result = grade_numbers(self.transcript("$43.56 a day, or $99 total", {"per_day": 43.55}))

        self.assertFalse(grade_result.passed)
        self.assertIn("99", grade_result.detail)
        self.assertNotIn("43.56", grade_result.detail)

    def test_tool_choice_needs_an_expected_tool_and_no_forbidden_one(self):
        transcript = self.transcript("ok", {})

        self.assertTrue(grade_tools(transcript, ["get_safe_to_spend"], []).passed)
        self.assertFalse(grade_tools(transcript, ["check_can_i_afford"], []).passed)
        self.assertFalse(grade_tools(transcript, [], ["get_safe_to_spend"]).passed)

    def test_boundary_needs_a_plain_refusal(self):
        self.assertTrue(grade_boundary(self.transcript("Subtrack can’t help with ETFs.")).passed)
        self.assertFalse(grade_boundary(self.transcript("ETFs are a great choice!")).passed)

    def test_boundary_is_only_graded_when_the_case_requires_it(self):
        names = [g.name for g in grade(self.transcript("hi"), {})]
        self.assertNotIn("advice_boundary", names)
        names = [g.name for g in grade(self.transcript("hi"), {"must_refuse": True})]
        self.assertIn("advice_boundary", names)


class EvalCaseFileTests(unittest.TestCase):
    def test_cases_are_unique_and_only_name_real_tools(self):
        cases = load_cases()
        tool_names = {tool["name"] for tool in TOOL_DEFINITIONS}

        self.assertGreaterEqual(len(cases), 30)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertIn(case["category"], {"numbers", "boundary", "confirmation"})
                named = case["expected_tools"] + case.get("forbidden_tools", [])
                self.assertLessEqual(set(named), tool_names)
                self.assertEqual(case.get("must_refuse", False), case["category"] == "boundary")


if __name__ == "__main__":
    unittest.main()
