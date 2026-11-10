import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import Transaction, UserPreference  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.middleware.auth import verify_token  # noqa: E402
from app.services import parse_rate_limit  # noqa: E402
from app.routers.transactions import ParseRequest, parse_transaction_text  # noqa: E402


def claude_returns(tool_input):
    block = SimpleNamespace(type="tool_use", input=tool_input)
    return patch(
        "app.services.transaction_parse.traced_call",
        return_value=SimpleNamespace(content=[block]),
    )


def draft(**fields):
    body = {
        "kind": "expense", "name": "Groceries", "amount": 40, "currency": "AUD",
        "category": "food", "occurred_on": "2026-11-09",
    }
    return {**body, **fields}


class TransactionParseTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(UserPreference(user_id="owner", base_currency="AUD", timezone="Australia/Sydney"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def parse(self, text="spent 40 on groceries yesterday"):
        return parse_transaction_text(ParseRequest(text=text), user_id="owner", db=self.db)

    def test_single_draft_is_returned_and_nothing_saved(self):
        with claude_returns({"drafts": [draft()]}):
            result = self.parse()
        self.assertEqual(result["drafts"][0]["amount"], 40.0)
        self.assertEqual(result["drafts"][0]["category"], "food")
        self.assertEqual(self.db.query(Transaction).count(), 0)

    def test_multiple_drafts(self):
        items = [draft(name="Lunch", amount=12), draft(name="Coffee", amount=5)]
        with claude_returns({"drafts": items}):
            result = self.parse("12 lunch and 5 coffee")
        self.assertEqual([item["name"] for item in result["drafts"]], ["Lunch", "Coffee"])

    def test_unknown_category_is_rejected_as_invalid(self):
        with claude_returns({"drafts": [draft(category="spaceships")]}):
            with self.assertRaises(HTTPException) as caught:
                self.parse()
        self.assertEqual(caught.exception.status_code, 422)

    def test_empty_output_is_422_and_writes_nothing(self):
        with claude_returns({"drafts": []}):
            with self.assertRaises(HTTPException) as caught:
                self.parse()
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(self.db.query(Transaction).count(), 0)

    def http(self):
        app.dependency_overrides[verify_token] = lambda: "owner"
        app.dependency_overrides[get_db] = lambda: self.db
        self.addCleanup(app.dependency_overrides.clear)
        parse_rate_limit.parse_calls.clear()
        self.addCleanup(parse_rate_limit.parse_calls.clear)
        return TestClient(app)

    def test_text_too_long_is_422(self):
        response = self.http().post("/transactions/parse", json={"text": "x" * 501})
        self.assertEqual(response.status_code, 422)

    def test_exceeding_the_rate_limit_is_429(self):
        client = self.http()
        with claude_returns({"drafts": [draft()]}):
            statuses = [
                client.post("/transactions/parse", json={"text": "40 groceries"}).status_code
                for _ in range(parse_rate_limit.PARSE_CALLS_PER_MINUTE + 1)
            ]
        self.assertEqual(statuses[:-1], [200] * parse_rate_limit.PARSE_CALLS_PER_MINUTE)
        self.assertEqual(statuses[-1], 429)


if __name__ == "__main__":
    unittest.main()
