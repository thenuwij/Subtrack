import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.agent.actions import confirm_action  # noqa: E402
from app.agent.tools import run_tool  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402
    AgentAction,
    AgentMessage,
    AgentThread,
    BillingCycle,
    Category,
    Subscription,
    Transaction,
    UserPreference,
)
from app.services.features import ALL_FEATURES  # noqa: E402

# One AUD buys 0.5 USD, so 10 USD is 20 AUD.
RATES = {"base": "AUD", "rates": {"USD": 0.5}, "stale": False, "fetched_at": "2026-11-03T00:00:00"}


class AgentTransactionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.thread = AgentThread(id=uuid4(), user_id="owner", title="Spending", next_message_sequence=1)
        self.message = AgentMessage(
            id=uuid4(), thread_id=self.thread.id, user_id="owner",
            role="assistant", sequence=1, content="", status="streaming",
        )
        self.db.add_all([
            self.thread,
            self.message,
            UserPreference(user_id="owner", base_currency="AUD", timezone="Australia/Sydney", enabled_features=list(ALL_FEATURES)),
        ])
        self.db.commit()
        for target in (
            "app.routers.rates.get_cached_rate_snapshot",
            "app.services.transactions.get_cached_rate_snapshot",
            "app.agent.finance.get_cached_rate_snapshot",
        ):
            patcher = patch(target, return_value=RATES)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def tool(self, name: str, payload: dict, user_id: str = "owner") -> dict:
        return run_tool(
            name, payload, self.db, user_id,
            thread_id=self.thread.id, assistant_message_id=self.message.id,
        )

    def log_payload(self, **fields) -> dict:
        return {
            "kind": "expense", "name": "Lunch", "amount": 20, "currency": "AUD",
            "category": "food", "occurred_on": "2026-11-10", "note": None,
            "recurring_payment_id": None, **fields,
        }

    def add_entry(self, user_id: str = "owner", **fields) -> Transaction:
        row = Transaction(
            user_id=user_id, kind="expense", name="Woolworths", amount=Decimal("42.10"),
            currency="AUD", base_amount=Decimal("42.10"), base_currency="AUD",
            category=Category.food, occurred_on=date(2026, 11, 10), source="manual", **fields,
        )
        self.db.add(row)
        self.db.commit()
        return row

    def add_payment(self, user_id: str = "owner") -> Subscription:
        payment = Subscription(
            user_id=user_id, name="AGL Energy", category=Category.utilities,
            amount=180.0, currency="AUD", cycle=BillingCycle.monthly,
            interval_unit="month", interval_count=1, is_active=True,
        )
        self.db.add(payment)
        self.db.commit()
        return payment

    def turn_spending_off(self):
        self.db.get(UserPreference, "owner").enabled_features = ["payments"]
        self.db.commit()

    def test_log_proposal_writes_nothing_until_confirmed(self):
        proposal = self.tool("propose_log_transaction", self.log_payload(amount=10, currency="USD"))

        self.assertEqual(proposal["status"], "pending")
        self.assertEqual(self.db.query(Transaction).count(), 0)

        confirm_action(self.db, "owner", proposal["id"])
        row = self.db.query(Transaction).one()
        self.assertEqual(row.source, "ai")
        self.assertEqual(row.base_amount, Decimal("20.00"))
        self.assertEqual(row.base_currency, "AUD")
        self.assertEqual(row.occurred_on, date(2026, 11, 10))

    def test_log_without_a_date_keeps_the_day_shown_on_the_card(self):
        with patch("app.agent.actions._local_today", return_value=date(2026, 11, 10)):
            proposal = self.tool("propose_log_transaction", self.log_payload(occurred_on=None))

        with patch("app.agent.actions._local_today", return_value=date(2026, 11, 11)):
            confirm_action(self.db, "owner", proposal["id"])

        self.assertIn("2026-11-10", proposal["description"])
        self.assertEqual(self.db.query(Transaction).one().occurred_on, date(2026, 11, 10))

    def test_log_proposal_warns_about_a_similar_entry(self):
        self.add_entry()

        proposal = self.tool("propose_log_transaction", self.log_payload(name="Woolworths", amount=42.10))

        self.assertIn("Looks like Woolworths AUD 42.10 on 10 Nov", proposal["description"])
        self.assertIn("confirm only if this is new", proposal["description"])

    def test_log_proposal_without_a_match_has_no_warning(self):
        self.add_entry()

        proposal = self.tool("propose_log_transaction", self.log_payload())

        self.assertNotIn("Looks like", proposal["description"])

    def test_log_links_only_an_owned_payment(self):
        other = self.add_payment(user_id="intruder")
        with self.assertRaises(HTTPException) as caught:
            self.tool("propose_log_transaction", self.log_payload(recurring_payment_id=str(other.id)))
        self.assertEqual(caught.exception.status_code, 404)

        own = self.add_payment()
        proposal = self.tool("propose_log_transaction", self.log_payload(
            name="AGL Energy", amount=180, recurring_payment_id=str(own.id),
        ))
        self.assertIn("tracked payment AGL Energy", proposal["description"])
        confirm_action(self.db, "owner", proposal["id"])
        self.assertEqual(self.db.query(Transaction).one().recurring_payment_id, own.id)

    def test_log_rejects_an_unsupported_currency(self):
        with self.assertRaises(ValidationError):
            self.tool("propose_log_transaction", self.log_payload(currency="XYZ"))

    def test_update_changes_the_entry_and_reconverts(self):
        row = self.add_entry()
        proposal = self.tool("propose_update_transaction", {
            "transaction_id": str(row.id), "amount": 10, "currency": "USD", "clear_fields": [],
        })
        self.assertEqual(self.db.get(Transaction, row.id).amount, Decimal("42.10"))

        confirm_action(self.db, "owner", proposal["id"])
        updated = self.db.get(Transaction, row.id)
        self.assertEqual((updated.amount, updated.currency), (Decimal("10.00"), "USD"))
        self.assertEqual(updated.base_amount, Decimal("20.00"))

    def test_update_can_clear_the_note(self):
        row = self.add_entry(note="Weekly shop")
        proposal = self.tool("propose_update_transaction", {
            "transaction_id": str(row.id), "clear_fields": ["note"],
        })

        confirm_action(self.db, "owner", proposal["id"])

        self.assertIsNone(self.db.get(Transaction, row.id).note)

    def test_update_and_remove_reject_entries_the_user_does_not_own(self):
        other = self.add_entry(user_id="intruder")
        for name, payload in (
            ("propose_update_transaction", {"transaction_id": str(other.id), "name": "Mine"}),
            ("propose_remove_transaction", {"transaction_id": str(other.id)}),
        ):
            with self.subTest(tool=name), self.assertRaises(HTTPException) as caught:
                self.tool(name, payload)
            self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.db.query(AgentAction).count(), 0)

    def test_update_and_remove_fail_when_the_entry_changed(self):
        row = self.add_entry()
        update = self.tool("propose_update_transaction", {"transaction_id": str(row.id), "name": "Coles"})
        remove = self.tool("propose_remove_transaction", {"transaction_id": str(row.id)})
        row.amount = Decimal("50.00")
        self.db.commit()

        for proposal in (update, remove):
            with self.subTest(action=proposal["action_type"]), self.assertRaises(HTTPException) as caught:
                confirm_action(self.db, "owner", proposal["id"])
            self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.db.get(Transaction, row.id).name, "Woolworths")

    def test_remove_deletes_the_entry_after_confirmation(self):
        row = self.add_entry()
        proposal = self.tool("propose_remove_transaction", {"transaction_id": str(row.id)})
        self.assertEqual(self.db.query(Transaction).count(), 1)

        confirm_action(self.db, "owner", proposal["id"])

        self.assertEqual(self.db.query(Transaction).count(), 0)

    def test_list_is_scoped_filtered_and_converted(self):
        self.add_entry()
        self.add_entry(user_id="intruder")
        self.db.add(Transaction(
            user_id="owner", kind="income", name="Salary", amount=Decimal("10.00"), currency="USD",
            category=Category.other, occurred_on=date(2026, 11, 1), source="manual",
        ))
        self.db.commit()

        result = self.tool("list_transactions", {"month": "2026-11"})
        expenses = self.tool("list_transactions", {"month": "2026-11", "kind": "expense"})

        self.assertEqual([entry["name"] for entry in result["transactions"]], ["Woolworths", "Salary"])
        self.assertEqual(result["transactions"][1]["amount_in_base"], 20.0)
        self.assertEqual(result["currency_conversion"]["status"], "current_rates")
        self.assertEqual([entry["name"] for entry in expenses["transactions"]], ["Woolworths"])

    def test_list_validates_its_input(self):
        self.assertIn("error", self.tool("list_transactions", {"month": "2026-13"}))
        self.assertIn("error", self.tool("list_transactions", {"limit": 500}))

    def test_list_reports_more_available_beyond_the_limit(self):
        self.add_entry()
        self.add_entry()

        result = self.tool("list_transactions", {"month": "2026-11", "limit": 1})

        self.assertEqual(result["returned_count"], 1)
        self.assertTrue(result["more_available"])

    def test_summary_uses_the_shared_monthly_totals(self):
        self.add_entry()
        self.db.add(Transaction(
            user_id="owner", kind="expense", name="Shop", amount=Decimal("5.00"), currency="EUR",
            category=Category.other, occurred_on=date(2026, 11, 2), source="manual",
        ))
        self.db.commit()

        result = self.tool("get_transaction_summary", {"month": "2026-11"})

        self.assertEqual(result["expenses"], 42.10)
        self.assertEqual(result["unconverted_count"], 1)
        self.assertEqual(result["currency_conversion"]["status"], "incomplete")

    def test_spending_off_returns_no_data_and_creates_no_proposal(self):
        row = self.add_entry()
        self.turn_spending_off()

        for name, payload in (
            ("list_transactions", {}),
            ("get_transaction_summary", {}),
            ("propose_log_transaction", self.log_payload()),
            ("propose_update_transaction", {"transaction_id": str(row.id), "name": "Coles"}),
            ("propose_remove_transaction", {"transaction_id": str(row.id)}),
        ):
            with self.subTest(tool=name):
                self.assertEqual(
                    self.tool(name, payload),
                    {"error": "Expenses and income is turned off in Settings."},
                )
        self.assertEqual(self.db.query(AgentAction).count(), 0)


if __name__ == "__main__":
    unittest.main()
