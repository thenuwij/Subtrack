import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import Subscription, UserPreference  # noqa: E402
from app.routers.subscriptions import BillParseRequest, parse_bill_text  # noqa: E402
from app.services import parse_rate_limit  # noqa: E402


def claude_returns(tool_input):
    block = SimpleNamespace(type="tool_use", input=tool_input)
    return patch("app.services.bill_parse.traced_call", return_value=SimpleNamespace(content=[block]))


def bill(**fields):
    body = {
        "name": "Rent", "amount": 400, "currency": "AUD", "category": "housing",
        "interval_unit": "week", "interval_count": 1,
    }
    return {**body, **fields}


class BillParseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(UserPreference(user_id="owner", base_currency="AUD", timezone="Australia/Sydney"))
        self.db.commit()
        parse_rate_limit.parse_calls.clear()
        self.addCleanup(parse_rate_limit.parse_calls.clear)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def parse(self, text="rent 400 weekly, phone 35 monthly on the 15th"):
        return parse_bill_text(BillParseRequest(text=text), user_id="owner", db=self.db)

    def test_bills_are_returned_and_nothing_saved(self):
        phone = bill(name="Phone", amount=35, category="phone_internet", interval_unit="month", next_due="2099-01-15")
        with claude_returns({"bills": [bill(), phone]}):
            result = self.parse()

        self.assertEqual([b["name"] for b in result["bills"]], ["Rent", "Phone"])
        self.assertEqual(result["bills"][0]["next_due"], None)
        self.assertEqual(result["bills"][1]["next_due"], "2099-01-15")
        self.assertEqual(self.db.query(Subscription).count(), 0)

    def test_a_past_next_charge_is_dropped_for_the_user_to_set(self):
        with claude_returns({"bills": [bill(next_due="2020-01-01")]}):
            result = self.parse()

        self.assertIsNone(result["bills"][0]["next_due"])

    def test_no_bills_or_invalid_bills_are_a_friendly_422(self):
        for tool_input in ({"bills": []}, {"bills": [bill(amount=-5)]}, {"bills": [bill(interval_unit="day")]}):
            with self.subTest(tool_input=tool_input), claude_returns(tool_input):
                with self.assertRaises(HTTPException) as caught:
                    self.parse()
                self.assertEqual(caught.exception.status_code, 422)

    def test_text_must_be_short_and_non_empty(self):
        for text in ("", "x" * 501):
            with self.subTest(length=len(text)), self.assertRaises(ValidationError):
                BillParseRequest(text=text)

    def test_parsing_is_rate_limited_per_user(self):
        with claude_returns({"bills": [bill()]}):
            for _ in range(parse_rate_limit.PARSE_CALLS_PER_MINUTE):
                self.parse()
            with self.assertRaises(HTTPException) as caught:
                self.parse()
        self.assertEqual(caught.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
