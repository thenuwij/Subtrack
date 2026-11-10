import os
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.agent.actions import confirm_action, create_action_proposal  # noqa: E402
from app.agent.tools import run_tool  # noqa: E402
from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402
    AgentMessage,
    AgentThread,
    SafeToSpendProfile,
    SetAside,
    Transaction,
    UserPreference,
)


class BudgetActionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.thread = AgentThread(id=uuid4(), user_id="owner", title="Money", next_message_sequence=1)
        self.message = AgentMessage(
            id=uuid4(), thread_id=self.thread.id, user_id="owner",
            role="assistant", sequence=1, content="", status="streaming",
        )
        self.db.add_all([
            self.thread, self.message,
            UserPreference(user_id="owner", base_currency="AUD", timezone="Australia/Sydney"),
            SafeToSpendProfile(
                user_id="owner", pay_amount=Decimal("1022.00"), currency="AUD",
                pay_anchor_on=date.today() + timedelta(days=5),
                pay_interval_unit="week", pay_interval_count=2, buffer=Decimal("0.00"),
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def propose(self, name: str, payload: dict) -> dict:
        return create_action_proposal(
            name, payload, self.db, "owner", thread_id=self.thread.id, assistant_message_id=self.message.id,
        )

    def confirm(self, action: dict) -> dict:
        return confirm_action(self.db, "owner", UUID(action["id"]))

    def budget(self, name="Groceries", amount="150.00", kind="pot", user_id="owner") -> SetAside:
        row = SetAside(id=uuid4(), user_id=user_id, kind=kind, name=name, amount_per_pay=Decimal(amount), currency="AUD")
        self.db.add(row)
        self.db.commit()
        return row

    def entry(self, kind="expense", amount="40.00", budget=None) -> Transaction:
        row = Transaction(
            id=uuid4(), user_id="owner", kind=kind, name="Coles", amount=Decimal(amount), currency="AUD",
            occurred_on=date.today(), set_aside_id=budget.id if budget else None,
        )
        self.db.add(row)
        self.db.commit()
        return row

    def test_adding_a_budget_waits_for_confirm(self):
        action = self.propose("propose_add_budget", {"kind": "pot", "name": "Eating out", "amount_per_pay": 60})

        self.assertEqual(action["summary"], "Add a budget: Eating out")
        self.assertEqual(self.db.query(SetAside).count(), 0)
        self.confirm(action)
        row = self.db.query(SetAside).one()
        self.assertEqual((row.name, row.amount_per_pay, row.currency), ("Eating out", Decimal("60.00"), "AUD"))

    def test_changing_a_budget_fails_safely_if_it_changed_meanwhile(self):
        row = self.budget()
        action = self.propose("propose_update_budget", {"budget_id": str(row.id), "amount_per_pay": 120})
        row.amount_per_pay = Decimal("130.00")
        self.db.commit()

        with self.assertRaises(HTTPException) as stale:
            self.confirm(action)

        self.assertEqual(stale.exception.status_code, 409)
        self.assertEqual(self.db.get(SetAside, row.id).amount_per_pay, Decimal("130.00"))

    def test_removing_a_budget_keeps_its_spends(self):
        row = self.budget()
        spend = self.entry(budget=row)

        self.confirm(self.propose("propose_remove_budget", {"budget_id": str(row.id)}))

        self.assertIsNone(self.db.get(SetAside, row.id))
        self.assertIsNone(self.db.get(Transaction, spend.id).set_aside_id)

    def test_a_spend_from_a_budget_has_no_category_and_others_do(self):
        row = self.budget()
        self.confirm(self.propose("propose_log_spend", {"name": "Coles", "amount": 45, "budget_id": str(row.id), "category": "transport"}))
        self.confirm(self.propose("propose_log_spend", {"name": "Uber", "amount": 18, "category": "transport"}))

        spends = {spend.name: spend for spend in self.db.query(Transaction).all()}
        self.assertEqual((spends["Coles"].set_aside_id, spends["Coles"].category.value), (row.id, "other"))
        self.assertEqual((spends["Uber"].set_aside_id, spends["Uber"].category.value), (None, "transport"))
        self.assertEqual(spends["Uber"].kind, "expense")

    def test_spends_cannot_use_income_or_come_out_of_a_saving(self):
        saving = self.budget(name="Trip", kind="save")
        with self.assertRaises(ValidationError):
            self.propose("propose_log_spend", {"name": "Oops", "amount": 5, "category": "income"})
        with self.assertRaises(HTTPException) as caught:
            self.propose("propose_log_spend", {"name": "Flights", "amount": 300, "budget_id": str(saving.id)})
        self.assertEqual(caught.exception.status_code, 422)

    def test_editing_and_undoing_a_logged_spend(self):
        row = self.budget()
        spend = self.entry(budget=row)

        self.confirm(self.propose(
            "propose_edit_logged_entry",
            {"spend_id": str(spend.id), "amount": 35, "remove_from_budget": True, "category": "food"},
        ))
        edited = self.db.get(Transaction, spend.id)
        self.assertEqual((edited.amount, edited.set_aside_id, edited.category.value), (Decimal("35.00"), None, "food"))

        self.confirm(self.propose("propose_remove_logged_entry", {"spend_id": str(spend.id)}))
        self.assertIsNone(self.db.get(Transaction, spend.id))

    def test_extra_income_is_logged_and_only_its_name_and_amount_change(self):
        self.confirm(self.propose("propose_log_extra_income", {"name": "Extra shift", "amount": 200}))
        income = self.db.query(Transaction).one()
        self.assertEqual((income.kind, income.category.value, income.amount), ("income", "income", Decimal("200.00")))

        with self.assertRaises(HTTPException) as caught:
            self.propose("propose_edit_logged_entry", {"spend_id": str(income.id), "category": "food"})
        self.assertEqual(caught.exception.status_code, 422)

    def test_pay_details_change_only_what_was_given(self):
        payday = date.today() + timedelta(days=7)
        self.confirm(self.propose(
            "propose_update_pay_details", {"pay_amount": 1100, "next_payday": payday.isoformat(), "schedule": "weekly"},
        ))

        profile = self.db.get(SafeToSpendProfile, "owner")
        self.assertEqual((profile.pay_amount, profile.pay_anchor_on), (Decimal("1100.00"), payday))
        self.assertEqual((profile.pay_interval_unit, profile.pay_interval_count, profile.buffer), ("week", 1, Decimal("0.00")))

    def test_a_past_payday_is_refused_in_the_users_own_timezone(self):
        sydney_today = datetime.now(ZoneInfo("Australia/Sydney")).date()
        with self.assertRaises(HTTPException) as caught:
            self.propose("propose_update_pay_details", {"next_payday": (sydney_today - timedelta(days=1)).isoformat()})
        self.assertEqual(caught.exception.status_code, 422)
        self.propose("propose_update_pay_details", {"next_payday": sydney_today.isoformat()})

    def test_other_peoples_budgets_and_spends_are_not_found(self):
        theirs = self.budget(user_id="someone-else")
        other_spend = Transaction(
            id=uuid4(), user_id="someone-else", kind="expense", name="Theirs", amount=Decimal("5"),
            currency="AUD", occurred_on=date.today(),
        )
        self.db.add(other_spend)
        self.db.commit()

        for name, payload in (
            ("propose_remove_budget", {"budget_id": str(theirs.id)}),
            ("propose_remove_logged_entry", {"spend_id": str(other_spend.id)}),
        ):
            with self.assertRaises(HTTPException) as caught:
                self.propose(name, payload)
            self.assertEqual(caught.exception.status_code, 404)

    def test_pay_cycles_tool_validates_its_count(self):
        self.assertIn("cycles", run_tool("get_pay_cycles", {"count": 2}, self.db, "owner"))
        self.assertIn("error", run_tool("get_pay_cycles", {"count": 40}, self.db, "owner"))


if __name__ == "__main__":
    unittest.main()
