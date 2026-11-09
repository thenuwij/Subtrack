import os
import unittest
from datetime import date, datetime
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
    Goal,
    Subscription,
    Transaction,
    UserPreference,
    WorkspacePage,
)
from app.routers.workspace import MAX_PAGES_PER_USER  # noqa: E402
from app.services.workspace_templates import TEMPLATES  # noqa: E402

RATES = {"base": "AUD", "rates": {"USD": 0.5}, "stale": False, "fetched_at": "2026-11-03T00:00:00"}
TODAY = date(2026, 11, 10)
WORKSPACE_OFF = {"error": "Custom workspace is turned off in Settings."}
MOVING_BLOCKS = [
    {"type": "upcoming_payments", "days": 30},
    {"type": "checklist", "items": [{"text": f"Task {n}"} for n in range(6)]},
    {"type": "notes"},
]


class AgentCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.thread = AgentThread(id=uuid4(), user_id="owner", title="Workspace", next_message_sequence=1)
        self.message = AgentMessage(
            id=uuid4(), thread_id=self.thread.id, user_id="owner",
            role="assistant", sequence=1, content="", status="streaming",
        )
        self.db.add_all([
            self.thread,
            self.message,
            UserPreference(user_id="owner", base_currency="AUD", timezone="Australia/Sydney"),
        ])
        self.db.commit()
        for target, value in (
            ("app.routers.rates.get_cached_rate_snapshot", RATES),
            ("app.services.transactions.get_cached_rate_snapshot", RATES),
            ("app.agent.actions._local_today", TODAY),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def tool(self, name: str, payload: dict) -> dict:
        return run_tool(
            name, payload, self.db, "owner",
            thread_id=self.thread.id, assistant_message_id=self.message.id,
        )

    def page_payload(self, **fields) -> dict:
        return {"title": "Moving out", "template_id": None, "blocks": MOVING_BLOCKS, **fields}

    def add_page(self, user_id: str = "owner", title: str = "Trip") -> WorkspacePage:
        page = WorkspacePage(
            user_id=user_id, title=title, template_id=None,
            blocks=[{"type": "notes", "title": None, "text": "Hello"}], position=0,
        )
        self.db.add(page)
        self.db.commit()
        return page

    def add_payment(self, user_id: str) -> str:
        payment = Subscription(
            id=uuid4(), user_id=user_id, name="Internet", category=Category.phone_internet, amount=80,
            cycle=BillingCycle.monthly, interval_unit="month", interval_count=1, currency="AUD",
            next_due=datetime(2026, 12, 1),
        )
        self.db.add(payment)
        self.db.commit()
        return str(payment.id)

    def turn_off(self, feature: str) -> None:
        pref = self.db.get(UserPreference, "owner")
        pref.enabled_features = [name for name in ("spending", "payments", "goals", "workspace") if name != feature]
        self.db.commit()

    def assert_confirm_fails(self, proposal: dict, status_code: int) -> HTTPException:
        with self.assertRaises(HTTPException) as caught:
            confirm_action(self.db, "owner", proposal["id"])
        self.assertEqual(caught.exception.status_code, status_code)
        return caught.exception


class AgentWorkspaceTests(AgentCase):
    def test_proposing_a_page_writes_nothing_until_confirmed(self):
        proposal = self.tool("propose_create_workspace_page", self.page_payload())

        self.assertEqual(proposal["status"], "pending")
        self.assertEqual(proposal["summary"], "Add page Moving out")
        self.assertIn("Upcoming payments (30 days), Checklist (6 items), Notes", proposal["description"])
        self.assertEqual(self.db.query(WorkspacePage).count(), 0)

        result = confirm_action(self.db, "owner", proposal["id"])

        page = self.db.query(WorkspacePage).one()
        self.assertEqual(result["result"]["page_id"], str(page.id))
        self.assertEqual(page.title, "Moving out")
        self.assertEqual([block["type"] for block in page.blocks], ["upcoming_payments", "checklist", "notes"])
        self.assertEqual(page.blocks[1]["items"][0], {"text": "Task 0", "done": False})

    def test_a_template_page_stores_the_blocks_the_card_lists(self):
        proposal = self.tool(
            "propose_create_workspace_page", self.page_payload(template_id="moving_house", blocks=None),
        )

        self.assertIn("Moving checklist (3 items), Bills to move (utilities)", proposal["description"])
        confirm_action(self.db, "owner", proposal["id"])
        page = self.db.query(WorkspacePage).one()
        self.assertEqual(page.template_id, "moving_house")
        self.assertEqual([b["type"] for b in page.blocks], [b["type"] for b in TEMPLATES["moving_house"].blocks])

    def test_unknown_block_types_and_config_are_rejected_at_proposal(self):
        for blocks in (
            [{"type": "investments"}],
            [{"type": "notes", "colour": "red"}],
            [{"type": "upcoming_payments", "days": 365}],
            [],
        ):
            with self.subTest(blocks=blocks), self.assertRaises(ValidationError):
                self.tool("propose_create_workspace_page", self.page_payload(blocks=blocks))
        with self.assertRaises(ValidationError):
            self.tool("propose_create_workspace_page", self.page_payload(blocks=None))
        self.assertEqual(self.db.query(AgentAction).count(), 0)

    def test_product_advice_in_page_text_is_refused_plainly(self):
        for payload in (
            self.page_payload(title="Investing in ETFs"),
            self.page_payload(blocks=[{"type": "checklist", "items": [{"text": "Buy shares in BHP"}]}]),
            self.page_payload(blocks=[{"type": "notes", "title": "Plan", "text": "Open a term deposit"}]),
            self.page_payload(blocks=[{"type": "notes", "title": "Crypto plan"}]),
        ):
            with self.subTest(payload=payload):
                result = self.tool("propose_create_workspace_page", payload)
                self.assertIn("can't include financial-product advice", result["error"])
        page = self.add_page()
        result = self.tool("propose_update_workspace_page", {
            "page_id": str(page.id), "title": "Switch your super", "blocks": None,
        })
        self.assertIn("financial-product advice", result["error"])
        self.assertEqual(self.db.query(AgentAction).count(), 0)

    def test_ordinary_page_text_is_allowed(self):
        proposal = self.tool("propose_create_workspace_page", self.page_payload(
            title="Save for a trip",
            blocks=[{"type": "checklist", "items": [{"text": "Pay off the credit card"}]}],
        ))

        self.assertEqual(proposal["status"], "pending")

    def test_others_payments_and_pages_return_404(self):
        theirs = self.add_payment("other")
        their_page = self.add_page("other")

        for name, payload in (
            ("propose_create_workspace_page", self.page_payload(
                blocks=[{"type": "payment_list", "payment_ids": [theirs]}],
            )),
            ("propose_update_workspace_page", {"page_id": str(their_page.id), "title": "Mine", "blocks": None}),
            ("propose_remove_workspace_page", {"page_id": str(their_page.id)}),
        ):
            with self.subTest(tool=name), self.assertRaises(HTTPException) as caught:
                self.tool(name, payload)
            self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.db.query(AgentAction).count(), 0)

    def test_owned_payment_ids_are_accepted(self):
        mine = self.add_payment("owner")

        proposal = self.tool("propose_create_workspace_page", self.page_payload(
            blocks=[{"type": "payment_list", "title": "Bills", "payment_ids": [mine]}],
        ))

        self.assertIn("Bills (1 payment)", proposal["description"])

    def test_update_and_remove_apply_only_after_confirmation(self):
        page = self.add_page()

        update = self.tool("propose_update_workspace_page", {
            "page_id": str(page.id), "title": "Japan trip", "blocks": [{"type": "spending_trend", "months": 3}],
        })
        self.assertIn("Rename it to Japan trip", update["description"])
        self.assertIn("Spending trend (3 months)", update["description"])
        self.assertEqual(self.db.get(WorkspacePage, page.id).title, "Trip")

        confirm_action(self.db, "owner", update["id"])
        self.db.refresh(page)
        self.assertEqual(page.title, "Japan trip")
        self.assertEqual(page.blocks, [{"type": "spending_trend", "title": None, "months": 3, "category": None}])

        remove = self.tool("propose_remove_workspace_page", {"page_id": str(page.id)})
        self.assertEqual(self.db.query(WorkspacePage).count(), 1)
        confirm_action(self.db, "owner", remove["id"])
        self.assertEqual(self.db.query(WorkspacePage).count(), 0)

    def test_a_page_changed_after_the_proposal_returns_409(self):
        page = self.add_page()
        for name, payload in (
            ("propose_update_workspace_page", {"page_id": str(page.id), "title": "Japan", "blocks": None}),
            ("propose_remove_workspace_page", {"page_id": str(page.id)}),
        ):
            with self.subTest(tool=name):
                proposal = self.tool(name, payload)
                page.title = f"Edited {name}"
                self.db.commit()

                self.assert_confirm_fails(proposal, 409)
                self.assertEqual(self.db.query(WorkspacePage).count(), 1)

    def test_page_limit_is_respected_at_proposal_and_confirmation(self):
        for _ in range(MAX_PAGES_PER_USER - 1):
            self.add_page()
        proposal = self.tool("propose_create_workspace_page", self.page_payload())
        self.add_page()

        self.assert_confirm_fails(proposal, 409)
        with self.assertRaises(HTTPException) as caught:
            self.tool("propose_create_workspace_page", self.page_payload(title="One more"))
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.db.query(WorkspacePage).count(), MAX_PAGES_PER_USER)

    def test_read_tools_list_templates_and_only_the_users_pages(self):
        mine = self.add_page()
        self.add_page("other")

        templates = self.tool("list_workspace_templates", {})["templates"]
        pages = self.tool("list_workspace_pages", {})["pages"]

        self.assertEqual({row["id"] for row in templates}, set(TEMPLATES))
        self.assertEqual([row["id"] for row in pages], [str(mine.id)])
        self.assertEqual(pages[0]["blocks"], mine.blocks)

    def test_workspace_off_refuses_every_workspace_tool(self):
        page = self.add_page()
        self.turn_off("workspace")

        for name, payload in (
            ("list_workspace_templates", {}),
            ("list_workspace_pages", {}),
            ("propose_create_workspace_page", self.page_payload()),
            ("propose_update_workspace_page", {"page_id": str(page.id), "title": "Japan", "blocks": None}),
            ("propose_remove_workspace_page", {"page_id": str(page.id)}),
        ):
            with self.subTest(tool=name):
                self.assertEqual(self.tool(name, payload), WORKSPACE_OFF)
        self.assertEqual(self.db.query(AgentAction).count(), 0)


class FeatureOffAtConfirmTests(AgentCase):
    """A card made while its feature was on can't be confirmed once the feature is off."""

    def test_spending_card_cannot_be_confirmed_after_spending_is_turned_off(self):
        proposal = self.tool("propose_log_transaction", {
            "kind": "expense", "name": "Lunch", "amount": 20, "currency": "AUD",
            "category": "food", "occurred_on": None, "note": None, "recurring_payment_id": None,
        })
        self.turn_off("spending")

        error = self.assert_confirm_fails(proposal, 403)
        self.assertEqual(error.detail, "Expenses and income is turned off in Settings.")
        self.assertEqual(self.db.query(Transaction).count(), 0)
        self.assertEqual(self.db.query(AgentAction).one().status, "failed")

    def test_goals_card_cannot_be_confirmed_after_goals_is_turned_off(self):
        proposal = self.tool("propose_create_goal", {
            "name": "Trip", "target_amount": 5000, "currency": "AUD", "target_date": None,
        })
        self.turn_off("goals")

        error = self.assert_confirm_fails(proposal, 403)
        self.assertEqual(error.detail, "Goals and budgets is turned off in Settings.")
        self.assertEqual(self.db.query(Goal).count(), 0)

    def test_workspace_card_cannot_be_confirmed_after_workspace_is_turned_off(self):
        proposal = self.tool("propose_create_workspace_page", self.page_payload())
        self.turn_off("workspace")

        error = self.assert_confirm_fails(proposal, 403)
        self.assertEqual(error.detail, WORKSPACE_OFF["error"])
        self.assertEqual(self.db.query(WorkspacePage).count(), 0)

    def test_a_card_confirms_while_its_feature_stays_on(self):
        proposal = self.tool("propose_create_goal", {
            "name": "Trip", "target_amount": 5000, "currency": "AUD", "target_date": None,
        })
        self.turn_off("workspace")

        confirm_action(self.db, "owner", proposal["id"])
        self.assertEqual(self.db.query(Goal).one().target_amount, Decimal("5000.00"))


if __name__ == "__main__":
    unittest.main()
