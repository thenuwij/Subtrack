import os
import unittest
from datetime import datetime
from typing import get_args
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import BillingCycle, Category, Goal, Subscription, UserPreference, WorkspacePage  # noqa: E402
from app.routers.workspace import (  # noqa: E402
    MAX_PAGES_PER_USER,
    WORKSPACE_OFF,
    PageCreate,
    PageUpdate,
    create_page,
    delete_page,
    get_page,
    list_pages,
    list_templates,
    router,
    update_page,
)
from app.services.workspace_blocks import validate_blocks  # noqa: E402
from app.services.workspace_templates import TEMPLATES, TemplateId  # noqa: E402

NOTES = {"type": "notes", "text": "Hello"}


def shared_costs(**changes) -> dict:
    block = {
        "type": "shared_costs",
        "people": ["Ana", "Ben"],
        "items": [{"label": "Rent", "amount": "1200.00", "paid_by": "Ana", "split_between": ["Ana", "Ben"]}],
        "currency": "AUD",
    }
    return {**block, **changes}


class BlockSchemaTests(unittest.TestCase):
    def test_every_block_type_accepts_its_config(self):
        blocks = validate_blocks([
            {"type": "payment_list", "category": "streaming", "payment_ids": [str(uuid4())], "title": "TV"},
            {"type": "transaction_log", "kind": "expense", "category": "food", "range": "last_month"},
            {"type": "budget", "categories": ["food", "transport"]},
            {"type": "goal_progress", "goal_ids": [str(uuid4())]},
            {"type": "upcoming_payments"},
            {"type": "spending_trend", "category": "food"},
            {"type": "checklist", "items": [{"text": "Pack", "done": True}]},
            shared_costs(),
            NOTES,
        ])

        self.assertEqual(blocks[4].days, 30)
        self.assertEqual(blocks[5].months, 6)
        self.assertEqual(len(blocks), 9)

    def test_unknown_types_and_config_keys_are_rejected(self):
        invalid = (
            {"type": "advice"},
            {"category": "food"},
            {"type": "notes", "colour": "red"},
            {"type": "checklist", "items": [{"text": "Pack", "priority": 1}]},
            shared_costs(items=[{
                "label": "Rent", "amount": "10", "paid_by": "Ana", "split_between": ["Ana"], "note": "x",
            }]),
            {"type": "transaction_log", "range": "last_year"},
            {"type": "budget", "categories": ["not_a_category"]},
        )
        for block in invalid:
            with self.subTest(block=block), self.assertRaises(ValidationError):
                validate_blocks([block])

    def test_strings_lists_and_numbers_are_bounded(self):
        invalid = (
            {"type": "notes", "text": "x" * 5001},
            {"type": "notes", "title": "x" * 81},
            {"type": "payment_list", "payment_ids": [str(uuid4()) for _ in range(51)]},
            {"type": "budget", "categories": ["food"] * 21},
            {"type": "goal_progress", "goal_ids": [str(uuid4()) for _ in range(21)]},
            {"type": "upcoming_payments", "days": 6},
            {"type": "upcoming_payments", "days": 91},
            {"type": "spending_trend", "months": 2},
            {"type": "spending_trend", "months": 13},
            {"type": "checklist", "items": [{"text": "x"}] * 51},
            {"type": "checklist", "items": [{"text": "x" * 201}]},
            shared_costs(people=[f"P{index}" for index in range(11)], items=[]),
            shared_costs(people=["x" * 61], items=[]),
            shared_costs(currency="NZD"),
        )
        for block in invalid:
            with self.subTest(block=str(block)[:80]), self.assertRaises(ValidationError):
                validate_blocks([block])

    def test_shared_cost_amounts_and_people_must_be_consistent(self):
        def item(**changes) -> dict:
            return {"label": "Rent", "amount": "10.00", "paid_by": "Ana", "split_between": ["Ana", "Ben"], **changes}

        invalid_items = (
            item(amount="0"), item(amount="1000000.01"), item(amount="1.001"),
            item(paid_by="Cara"), item(split_between=[]), item(split_between=["Ana", "Cara"]),
            item(split_between=["Ana", "Ana"]),
        )
        for bad in invalid_items:
            with self.subTest(item=bad), self.assertRaises(ValidationError):
                validate_blocks([shared_costs(items=[bad])])
        with self.assertRaises(ValidationError):
            validate_blocks([shared_costs(people=["Ana", "Ana"], items=[])])
        with self.assertRaises(ValidationError):
            validate_blocks([shared_costs(items=[item()] * 51)])

    def test_a_page_has_between_one_and_twenty_blocks(self):
        validate_blocks([NOTES] * 20)
        for blocks in ([], [NOTES] * 21):
            with self.assertRaises(ValidationError):
                validate_blocks(blocks)
            with self.assertRaises(ValidationError):
                PageCreate(title="Page", blocks=blocks)


class TemplateTests(unittest.TestCase):
    def test_every_template_id_has_one_template_whose_layout_validates(self):
        self.assertEqual(set(TEMPLATES), set(get_args(TemplateId)))
        for template_id, template in TEMPLATES.items():
            with self.subTest(template=template_id):
                self.assertEqual(template.id, template_id)
                self.assertTrue(validate_blocks(list(template.blocks)))

    def test_debt_payoff_only_tracks_the_users_own_entries(self):
        block_types = {block["type"] for block in TEMPLATES["debt_payoff"].blocks}

        self.assertLessEqual(block_types, {"payment_list", "transaction_log", "checklist", "notes"})


class WorkspaceApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create(self, user_id="owner", **fields):
        body = {"title": "My page", **fields}
        return create_page(PageCreate(**body), user_id=user_id, db=self.db)

    def add_payment(self, user_id: str) -> str:
        payment = Subscription(
            id=uuid4(), user_id=user_id, name="Netflix", category=Category.streaming, amount=20,
            cycle=BillingCycle.monthly, interval_unit="month", interval_count=1, currency="AUD",
            next_due=datetime(2026, 12, 1),
        )
        self.db.add(payment)
        self.db.commit()
        return str(payment.id)

    def add_goal(self, user_id: str) -> str:
        goal = Goal(id=uuid4(), user_id=user_id, name="Trip", target_amount=900, currency="AUD")
        self.db.add(goal)
        self.db.commit()
        return str(goal.id)

    def test_templates_list_their_block_types(self):
        templates = {row["id"]: row for row in list_templates(user_id="owner", db=self.db)}

        self.assertEqual(set(templates), set(TEMPLATES))
        self.assertEqual(templates["monthly_budget"]["block_types"][0], "budget")
        self.assertTrue(all(row["name"] and row["description"] for row in templates.values()))

    def test_creating_from_a_template_copies_its_blocks(self):
        for template_id, template in TEMPLATES.items():
            with self.subTest(template=template_id):
                page = self.create(template_id=template_id)

                self.assertEqual(page["template_id"], template_id)
                self.assertEqual([block["type"] for block in page["blocks"]], [b["type"] for b in template.blocks])
                self.assertEqual(get_page(UUID(page["id"]), user_id="owner", db=self.db)["blocks"], page["blocks"])

    def test_explicit_blocks_replace_the_template_layout(self):
        page = self.create(template_id="moving_house", blocks=[NOTES])

        self.assertEqual(page["template_id"], "moving_house")
        self.assertEqual(page["blocks"], [{"type": "notes", "title": None, "text": "Hello"}])

    def test_a_page_needs_a_title_and_a_known_template_or_blocks(self):
        for body in ({"title": "Page"}, {"blocks": [NOTES]}, {"title": "", "blocks": [NOTES]},
                     {"title": "x" * 121, "blocks": [NOTES]}, {"title": "Page", "template_id": "unknown"},
                     {"title": "Page", "blocks": [NOTES], "owner": "me"}):
            with self.subTest(body=body), self.assertRaises(ValidationError):
                PageCreate(**body)
        with self.assertRaises(ValidationError):
            PageUpdate(title=None)

    def test_pages_list_in_position_order_and_new_pages_go_last(self):
        first = self.create(title="First", blocks=[NOTES])
        second = self.create(title="Second", template_id="trip_budget")

        self.assertEqual((first["position"], second["position"]), (0, 1))
        update_page(UUID(first["id"]), PageUpdate(position=5), user_id="owner", db=self.db)

        listed = list_pages(user_id="owner", db=self.db)
        self.assertEqual([row["title"] for row in listed], ["Second", "First"])
        self.assertEqual(listed[0]["block_count"], len(TEMPLATES["trip_budget"].blocks))
        self.assertEqual(self.create(title="Third", blocks=[NOTES])["position"], 6)

    def test_update_changes_title_and_blocks_and_delete_removes_the_page(self):
        page = self.create(blocks=[NOTES])
        page_id = UUID(page["id"])

        updated = update_page(
            page_id, PageUpdate(title="Renamed", blocks=[{"type": "upcoming_payments", "days": 14}]),
            user_id="owner", db=self.db,
        )

        self.assertEqual(updated["title"], "Renamed")
        self.assertEqual(updated["blocks"], [{"type": "upcoming_payments", "title": None, "days": 14}])
        delete_page(page_id, user_id="owner", db=self.db)
        self.assertEqual(self.db.query(WorkspacePage).count(), 0)

    def test_page_limit_per_user(self):
        for _ in range(MAX_PAGES_PER_USER):
            self.create(blocks=[NOTES])

        with self.assertRaises(HTTPException) as caught:
            self.create(blocks=[NOTES])
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.create(user_id="other", blocks=[NOTES])["position"], 0)

    def test_other_users_pages_return_404(self):
        theirs = UUID(self.create(user_id="other", blocks=[NOTES])["id"])
        mine = self.create(blocks=[NOTES])

        self.assertEqual([row["id"] for row in list_pages(user_id="owner", db=self.db)], [mine["id"]])
        for action in (
            lambda: get_page(theirs, user_id="owner", db=self.db),
            lambda: update_page(theirs, PageUpdate(title="Mine"), user_id="owner", db=self.db),
            lambda: delete_page(theirs, user_id="owner", db=self.db),
        ):
            with self.assertRaises(HTTPException) as caught:
                action()
            self.assertEqual(caught.exception.status_code, 404)

    def test_referenced_payments_and_goals_must_belong_to_the_user(self):
        my_payment, their_payment = self.add_payment("owner"), self.add_payment("other")
        my_goal, their_goal = self.add_goal("owner"), self.add_goal("other")
        page = self.create(blocks=[
            {"type": "payment_list", "payment_ids": [my_payment]},
            {"type": "goal_progress", "goal_ids": [my_goal]},
        ])

        for blocks in (
            [{"type": "payment_list", "payment_ids": [my_payment, their_payment]}],
            [{"type": "payment_list", "payment_ids": [str(uuid4())]}],
            [{"type": "goal_progress", "goal_ids": [their_goal]}],
        ):
            with self.subTest(blocks=blocks):
                for action in (
                    lambda blocks=blocks: self.create(blocks=blocks),
                    lambda blocks=blocks: update_page(
                        UUID(page["id"]), PageUpdate(blocks=blocks), user_id="owner", db=self.db,
                    ),
                ):
                    with self.assertRaises(HTTPException) as caught:
                        action()
                    self.assertEqual(caught.exception.status_code, 404)

    def test_every_route_refuses_when_workspace_is_off(self):
        page_id = UUID(self.create(blocks=[NOTES])["id"])
        self.db.add(UserPreference(user_id="owner", base_currency="AUD", enabled_features=["spending"]))
        self.db.commit()
        gated = (
            lambda: list_templates(user_id="owner", db=self.db),
            lambda: list_pages(user_id="owner", db=self.db),
            lambda: self.create(blocks=[NOTES]),
            lambda: get_page(page_id, user_id="owner", db=self.db),
            lambda: update_page(page_id, PageUpdate(title="New"), user_id="owner", db=self.db),
            lambda: delete_page(page_id, user_id="owner", db=self.db),
        )

        self.assertEqual(len(gated), len(router.routes))
        for action in gated:
            with self.assertRaises(HTTPException) as caught:
                action()
            self.assertEqual(caught.exception.status_code, 403)
            self.assertEqual(caught.exception.detail, WORKSPACE_OFF)


if __name__ == "__main__":
    unittest.main()
