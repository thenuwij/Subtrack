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
    Budget,
    Category,
    Goal,
    GoalContribution,
    Transaction,
    UserPreference,
)
from app.services.features import ALL_FEATURES  # noqa: E402

RATES = {"base": "AUD", "rates": {"USD": 0.5}, "stale": False, "fetched_at": "2026-11-03T00:00:00"}
TODAY = date(2026, 11, 10)
GOALS_OFF = {"error": "Goals and budgets is turned off in Settings."}


class AgentGoalTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.thread = AgentThread(id=uuid4(), user_id="owner", title="Goals", next_message_sequence=1)
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
        for target, value in (
            ("app.routers.rates.get_cached_rate_snapshot", RATES),
            ("app.services.transactions.get_cached_rate_snapshot", RATES),
            ("app.services.budgets.get_cached_rate_snapshot", RATES),
            ("app.agent.actions._local_today", TODAY),
            ("app.routers.goals._today", TODAY),
        ):
            patcher = patch(target, return_value=value)
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

    def add_budget(self, user_id: str = "owner", category: Category = Category.food, limit: str = "300.00") -> Budget:
        row = Budget(user_id=user_id, category=category, monthly_limit=Decimal(limit), currency="AUD")
        self.db.add(row)
        self.db.commit()
        return row

    def add_goal(self, user_id: str = "owner", saved: str | None = None, **fields) -> Goal:
        goal = Goal(**{
            "user_id": user_id, "name": "Trip", "target_amount": Decimal("5000.00"),
            "currency": "AUD", "target_date": date(2026, 12, 8), **fields,
        })
        self.db.add(goal)
        self.db.flush()
        if saved is not None:
            self.db.add(GoalContribution(
                goal_id=goal.id, user_id=user_id, amount=Decimal(saved),
                occurred_on=date(2026, 11, 1), source="manual",
            ))
        self.db.commit()
        return goal

    def contribution_payload(self, goal: Goal, amount: float = 100, **fields) -> dict:
        return {"goal_id": str(goal.id), "amount": amount, "occurred_on": None, "note": None, **fields}

    def goal_payload(self, **fields) -> dict:
        return {
            "name": "Trip", "target_amount": 5000, "currency": "aud", "target_date": "2027-06-30", **fields,
        }

    def test_set_budget_writes_nothing_until_confirmed(self):
        proposal = self.tool("propose_set_budget", {"category": "food", "monthly_limit": 400})

        self.assertEqual(proposal["status"], "pending")
        self.assertIn("monthly food budget of AUD 400.00", proposal["description"])
        self.assertEqual(self.db.query(Budget).count(), 0)

        confirm_action(self.db, "owner", proposal["id"])
        row = self.db.query(Budget).one()
        self.assertEqual((row.category, row.monthly_limit, row.currency), (Category.food, Decimal("400.00"), "AUD"))

    def test_set_budget_updates_the_existing_budget_for_that_category(self):
        existing = self.add_budget()

        proposal = self.tool("propose_set_budget", {"category": "food", "monthly_limit": 400})
        self.assertIn("from AUD 300.00 to AUD 400.00", proposal["description"])
        confirm_action(self.db, "owner", proposal["id"])

        row = self.db.query(Budget).one()
        self.assertEqual((row.id, row.monthly_limit), (existing.id, Decimal("400.00")))

    def test_set_budget_fails_when_the_budget_or_base_currency_changed(self):
        budget = self.add_budget()
        changed_limit = self.tool("propose_set_budget", {"category": "food", "monthly_limit": 400})
        budget.monthly_limit = Decimal("350.00")
        self.db.commit()
        changed_base = self.tool("propose_set_budget", {"category": "travel", "monthly_limit": 200})
        self.db.get(UserPreference, "owner").base_currency = "USD"
        self.db.commit()

        for proposal in (changed_limit, changed_base):
            with self.subTest(summary=proposal["summary"]), self.assertRaises(HTTPException) as caught:
                confirm_action(self.db, "owner", proposal["id"])
            self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.db.query(Budget).count(), 1)

    def test_remove_budget_deletes_it_after_confirmation(self):
        budget = self.add_budget()
        proposal = self.tool("propose_remove_budget", {"budget_id": str(budget.id)})
        self.assertEqual(self.db.query(Budget).count(), 1)

        confirm_action(self.db, "owner", proposal["id"])

        self.assertEqual(self.db.query(Budget).count(), 0)

    def test_budget_status_uses_the_shared_service(self):
        self.add_budget()
        self.add_budget(user_id="intruder")
        self.db.add(Transaction(
            user_id="owner", kind="expense", name="Woolworths", amount=Decimal("120.00"), currency="AUD",
            base_amount=Decimal("120.00"), base_currency="AUD", category=Category.food,
            occurred_on=date(2026, 11, 4), source="manual",
        ))
        self.db.commit()

        result = self.tool("get_budget_status", {"month": "2026-11"})

        self.assertEqual(len(result["budgets"]), 1)
        self.assertEqual((result["budgets"][0]["spent"], result["budgets"][0]["left"]), (120.0, 180.0))
        self.assertIn("error", self.tool("get_budget_status", {"month": "2026-13"}))

    def test_create_goal_writes_nothing_until_confirmed(self):
        proposal = self.tool("propose_create_goal", self.goal_payload())

        self.assertEqual(proposal["description"], "Save AUD 5000.00 for Trip by 2027-06-30.")
        self.assertEqual(self.db.query(Goal).count(), 0)

        confirm_action(self.db, "owner", proposal["id"])
        goal = self.db.query(Goal).one()
        self.assertEqual((goal.name, goal.currency, goal.target_date), ("Trip", "AUD", date(2027, 6, 30)))

    def test_create_goal_rejects_an_unsupported_currency(self):
        with self.assertRaises(ValidationError):
            self.tool("propose_create_goal", self.goal_payload(currency="XYZ"))

    def test_update_goal_can_archive_and_clear_the_date(self):
        goal = self.add_goal()
        proposal = self.tool("propose_update_goal", {
            "goal_id": str(goal.id), "target_amount": 6000, "archived": True, "clear_fields": ["target_date"],
        })
        self.assertIsNone(self.db.get(Goal, goal.id).archived_at)

        confirm_action(self.db, "owner", proposal["id"])

        updated = self.db.get(Goal, goal.id)
        self.assertEqual(updated.target_amount, Decimal("6000.00"))
        self.assertIsNone(updated.target_date)
        self.assertIsNotNone(updated.archived_at)

    def test_remove_goal_deletes_it_and_its_contributions(self):
        goal = self.add_goal(saved="250.00")
        proposal = self.tool("propose_remove_goal", {"goal_id": str(goal.id)})
        self.assertIn("1 contributions (AUD 250.00 saved)", proposal["description"])

        confirm_action(self.db, "owner", proposal["id"])

        self.assertEqual((self.db.query(Goal).count(), self.db.query(GoalContribution).count()), (0, 0))

    def test_contribution_card_shows_the_service_computed_total_and_weekly_amount(self):
        # 28 days before the target is 4 weekly deposits: (5000 - 1100) / 4 = 975.
        goal = self.add_goal(saved="1000.00")

        proposal = self.tool("propose_add_goal_contribution", self.contribution_payload(goal))

        self.assertEqual(self.db.query(GoalContribution).count(), 1)
        self.assertIn("Saved will be AUD 1100.00 of AUD 5000.00", proposal["description"])
        self.assertIn("AUD 975.00 a week to reach it by 2026-12-08", proposal["description"])

        result = confirm_action(self.db, "owner", proposal["id"])
        added = self.db.query(GoalContribution).filter(GoalContribution.source == "ai").one()
        self.assertEqual((added.amount, added.occurred_on), (Decimal("100.00"), TODAY))
        self.assertEqual(result["result"]["saved"], 1100.0)

    def test_contribution_that_would_make_the_balance_negative_is_rejected(self):
        goal = self.add_goal(saved="50.00")

        with self.assertRaises(HTTPException) as caught:
            self.tool("propose_add_goal_contribution", self.contribution_payload(goal, amount=-80))

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.db.query(AgentAction).count(), 0)

    def test_withdrawal_within_the_balance_is_allowed(self):
        goal = self.add_goal(saved="50.00")

        proposal = self.tool("propose_add_goal_contribution", self.contribution_payload(goal, amount=-20))
        confirm_action(self.db, "owner", proposal["id"])

        self.assertIn("Take AUD 20.00 out of Trip", proposal["description"])
        self.assertEqual(self.db.query(GoalContribution).count(), 2)

    def test_goal_changes_fail_when_the_goal_changed(self):
        goal = self.add_goal(saved="100.00")
        proposals = [
            self.tool("propose_update_goal", {"goal_id": str(goal.id), "name": "Japan"}),
            self.tool("propose_remove_goal", {"goal_id": str(goal.id)}),
            self.tool("propose_add_goal_contribution", self.contribution_payload(goal)),
        ]
        self.db.add(GoalContribution(
            goal_id=goal.id, user_id="owner", amount=Decimal("10.00"),
            occurred_on=date(2026, 11, 9), source="manual",
        ))
        self.db.commit()

        for proposal in proposals:
            with self.subTest(action=proposal["action_type"]), self.assertRaises(HTTPException) as caught:
                confirm_action(self.db, "owner", proposal["id"])
            self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.db.get(Goal, goal.id).name, "Trip")
        self.assertEqual(self.db.query(GoalContribution).count(), 2)

    def test_other_users_budgets_and_goals_are_rejected(self):
        budget = self.add_budget(user_id="intruder")
        goal = self.add_goal(user_id="intruder")
        for name, payload in (
            ("propose_remove_budget", {"budget_id": str(budget.id)}),
            ("propose_update_goal", {"goal_id": str(goal.id), "name": "Mine"}),
            ("propose_remove_goal", {"goal_id": str(goal.id)}),
            ("propose_add_goal_contribution", self.contribution_payload(goal)),
        ):
            with self.subTest(tool=name), self.assertRaises(HTTPException) as caught:
                self.tool(name, payload)
            self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.db.query(AgentAction).count(), 0)

    def test_list_goals_is_scoped_and_hides_archived_by_default(self):
        self.add_goal(saved="1000.00")
        self.add_goal(name="Old car", archived_at=TODAY)
        self.add_goal(user_id="intruder")

        active = self.tool("list_goals", {})
        everything = self.tool("list_goals", {"include_archived": True})

        self.assertEqual([goal["name"] for goal in active["goals"]], ["Trip"])
        self.assertEqual(active["goals"][0]["needed_per_week"], 1000.0)
        self.assertEqual(len(everything["goals"]), 2)

    def test_goals_off_returns_no_data_and_creates_no_proposal(self):
        budget = self.add_budget()
        goal = self.add_goal()
        self.db.get(UserPreference, "owner").enabled_features = ["spending"]
        self.db.commit()

        for name, payload in (
            ("get_budget_status", {}),
            ("list_goals", {}),
            ("propose_set_budget", {"category": "food", "monthly_limit": 400}),
            ("propose_remove_budget", {"budget_id": str(budget.id)}),
            ("propose_create_goal", self.goal_payload()),
            ("propose_update_goal", {"goal_id": str(goal.id), "name": "Japan"}),
            ("propose_remove_goal", {"goal_id": str(goal.id)}),
            ("propose_add_goal_contribution", self.contribution_payload(goal)),
        ):
            with self.subTest(tool=name):
                self.assertEqual(self.tool(name, payload), GOALS_OFF)
        self.assertEqual(self.db.query(AgentAction).count(), 0)



class GoalGuardrailTests(unittest.TestCase):
    def test_rules_forbid_suggesting_where_to_keep_goal_savings(self):
        from app.routers.agent import SYSTEM_RULES

        self.assertIn("not a financial product", SYSTEM_RULES)
        self.assertIn("Never suggest where to keep the money", SYSTEM_RULES)
        self.assertIn("Do not recommend or compare investments", SYSTEM_RULES)


if __name__ == "__main__":
    unittest.main()
