import os
import unittest
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import Goal, GoalContribution, UserPreference  # noqa: E402
from app.routers.goals import (  # noqa: E402
    ContributionCreate,
    GoalCreate,
    GoalUpdate,
    add_contribution,
    create_goal,
    delete_contribution,
    delete_goal,
    list_goals,
    update_goal,
)
from app.services.goals import goal_progress  # noqa: E402

TODAY = date(2026, 11, 10)


def goal(target="1000.00", target_date=None) -> Goal:
    return Goal(name="Holiday", target_amount=Decimal(target), currency="AUD", target_date=target_date)


class GoalProgressTests(unittest.TestCase):
    def test_future_target_date_gives_weekly_and_daily_amounts_rounded_up(self):
        progress = goal_progress(goal(target_date=date(2026, 12, 1)), Decimal("300"), TODAY)

        self.assertEqual(progress["saved"], 300.0)
        self.assertEqual(progress["remaining"], 700.0)
        self.assertEqual(progress["percent"], 30.0)
        self.assertEqual(progress["status"], "on_the_way")
        self.assertEqual(progress["days_left"], 21)
        self.assertEqual(progress["weeks_left"], 3)
        self.assertEqual(progress["needed_per_week"], 233.34)
        self.assertEqual(progress["needed_per_day"], 33.34)

    def test_a_partial_week_counts_as_one_weekly_deposit(self):
        progress = goal_progress(goal(target_date=date(2026, 11, 15)), Decimal("0"), TODAY)

        self.assertEqual(progress["weeks_left"], 1)
        self.assertEqual(progress["needed_per_week"], 1000.0)
        self.assertEqual(progress["needed_per_day"], 200.0)

    def test_no_weekly_amount_for_a_past_target_date(self):
        progress = goal_progress(goal(target_date=date(2026, 11, 1)), Decimal("100"), TODAY)

        self.assertEqual(progress["status"], "target_date_passed")
        self.assertIsNone(progress["needed_per_week"])
        self.assertIsNone(progress["needed_per_day"])
        self.assertEqual(progress["remaining"], 900.0)

    def test_no_weekly_amount_once_the_goal_is_reached(self):
        progress = goal_progress(goal(target_date=date(2027, 1, 1)), Decimal("1200"), TODAY)

        self.assertEqual(progress["status"], "reached")
        self.assertEqual(progress["remaining"], 0.0)
        self.assertEqual(progress["percent"], 120.0)
        self.assertIsNone(progress["needed_per_week"])

    def test_target_date_today_and_no_target_date(self):
        self.assertEqual(goal_progress(goal(target_date=TODAY), Decimal("0"), TODAY)["status"], "due_today")
        without_date = goal_progress(goal(), Decimal("0"), TODAY)
        self.assertEqual(without_date["status"], "no_target_date")
        self.assertIsNone(without_date["needed_per_week"])


class GoalApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(UserPreference(user_id="owner", base_currency="AUD", timezone="Australia/Sydney"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create(self, user_id="owner", **fields):
        body = {"name": "Holiday", "target_amount": "1000.00", "currency": "AUD", **fields}
        return create_goal(GoalCreate(**body), user_id=user_id, db=self.db)

    def contribute(self, goal_id, amount, user_id="owner"):
        return add_contribution(
            UUID(goal_id), ContributionCreate(amount=amount, occurred_on="2026-11-01"),
            user_id=user_id, db=self.db,
        )

    def test_contributions_add_up_and_withdrawals_reduce_saved(self):
        created = self.create()
        self.contribute(created["id"], "300.00")
        added = self.contribute(created["id"], "-50.00")

        self.assertEqual(added["goal"]["saved"], 250.0)
        self.assertEqual(added["source"], "manual")
        self.assertEqual(len(list_goals(user_id="owner", db=self.db)[0]["contributions"]), 2)

    def test_cannot_take_out_more_than_has_been_saved(self):
        created = self.create()
        deposit = self.contribute(created["id"], "100.00")
        self.contribute(created["id"], "-80.00")

        for action in (
            lambda: self.contribute(created["id"], "-20.01"),
            lambda: delete_contribution(
                UUID(created["id"]), UUID(deposit["id"]), user_id="owner", db=self.db,
            ),
        ):
            with self.assertRaises(HTTPException) as caught:
                action()
            self.assertEqual(caught.exception.status_code, 409)

    def test_contribution_amount_must_be_non_zero_and_in_cents(self):
        for amount in ("0", "0.001", "NaN", "1000000.01"):
            with self.assertRaises(ValidationError):
                ContributionCreate(amount=amount)

    def test_goal_input_is_bounded(self):
        base = {"name": "Holiday", "target_amount": "10", "currency": "AUD"}
        invalid = (
            {"name": ""}, {"name": "x" * 121}, {"target_amount": "0"},
            {"currency": "NZD"}, {"target_date": "2101-01-01"}, {"source": "ai"},
        )
        for change in invalid:
            with self.assertRaises(ValidationError):
                GoalCreate(**{**base, **change})
        with self.assertRaises(ValidationError):
            GoalUpdate(currency="USD")
        with self.assertRaises(ValidationError):
            GoalUpdate(name=None)

    def test_update_clears_target_date_and_archives(self):
        created = self.create(target_date="2027-01-01")

        updated = update_goal(
            UUID(created["id"]), GoalUpdate(target_date=None, archived=True, target_amount="500"),
            user_id="owner", db=self.db,
        )

        self.assertIsNone(updated["target_date"])
        self.assertIsNotNone(updated["archived_at"])
        self.assertEqual(updated["target_amount"], 500.0)
        self.assertEqual(list_goals(user_id="owner", db=self.db), [])
        self.assertEqual(len(list_goals(include_archived=True, user_id="owner", db=self.db)), 1)

    def test_deleting_a_goal_removes_its_contributions(self):
        created = self.create()
        self.contribute(created["id"], "10.00")

        delete_goal(UUID(created["id"]), user_id="owner", db=self.db)

        self.assertEqual(self.db.query(GoalContribution).count(), 0)

    def test_other_users_goals_and_contributions_return_404(self):
        theirs = self.create(user_id="other")
        their_contribution = self.contribute(theirs["id"], "10.00", user_id="other")
        mine = self.create()
        goal_id = UUID(theirs["id"])

        self.assertEqual([row["id"] for row in list_goals(user_id="owner", db=self.db)], [mine["id"]])
        for action in (
            lambda: update_goal(goal_id, GoalUpdate(name="Mine"), user_id="owner", db=self.db),
            lambda: delete_goal(goal_id, user_id="owner", db=self.db),
            lambda: self.contribute(theirs["id"], "5.00"),
            lambda: delete_contribution(goal_id, UUID(their_contribution["id"]), user_id="owner", db=self.db),
            lambda: delete_contribution(
                UUID(mine["id"]), UUID(their_contribution["id"]), user_id="owner", db=self.db,
            ),
        ):
            with self.assertRaises(HTTPException) as caught:
                action()
            self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
