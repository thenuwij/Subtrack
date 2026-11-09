import os
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402
    BillingCycle,
    Budget,
    Category,
    Goal,
    GoalContribution,
    Subscription,
    Transaction,
    UserPreference,
)
from app.routers.goals import list_goals  # noqa: E402
from app.routers.subscriptions import get_upcoming_forecast  # noqa: E402
from app.routers.workspace import WORKSPACE_OFF, PageCreate, create_page, get_page_data  # noqa: E402
from app.services import workspace_data  # noqa: E402
from app.services.budgets import budget_status  # noqa: E402
from app.services.transactions import month_summary  # noqa: E402
from app.services.workspace_data import BLOCK_FAILED, resolve_page_blocks  # noqa: E402

# One AUD buys 0.5 USD, so 10 USD is 20 AUD. There is no GBP rate.
RATES = {"base": "AUD", "rates": {"USD": 0.5}, "stale": False, "fetched_at": "2026-11-03T00:00:00"}


def previous_month(day: date) -> date:
    return (day.replace(day=1) - timedelta(days=1)).replace(day=5)


class WorkspaceDataTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(UserPreference(user_id="owner", base_currency="AUD", timezone="UTC"))
        self.db.commit()
        for target in (
            "app.routers.rates.get_cached_rate_snapshot",
            "app.services.budgets.get_cached_rate_snapshot",
            "app.services.transactions.get_cached_rate_snapshot",
            "app.services.workspace_data.get_cached_rate_snapshot",
            "app.agent.finance.get_cached_rate_snapshot",
        ):
            patcher = patch(target, return_value=RATES)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.today = datetime.now(timezone.utc).date()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def resolve(self, *blocks: dict, user_id: str = "owner") -> list[dict]:
        return resolve_page_blocks(self.db, user_id, list(blocks), today=self.today)

    def data(self, block: dict) -> dict:
        resolved = self.resolve(block)[0]
        self.assertNotIn("error", resolved)
        return resolved["data"]

    def payment(self, name="Netflix", amount=20.0, currency="AUD", category=Category.streaming,
                user_id="owner", due_in_days=5) -> Subscription:
        row = Subscription(
            id=uuid4(), user_id=user_id, name=name, category=category, amount=amount, currency=currency,
            cycle=BillingCycle.monthly, interval_unit="month", interval_count=1, is_active=True,
            next_due=datetime.combine(self.today + timedelta(days=due_in_days), datetime.min.time()),
        )
        self.db.add(row)
        self.db.commit()
        return row

    def entry(self, amount, kind="expense", currency="AUD", category=Category.food, on=None, user_id="owner"):
        self.db.add(Transaction(
            user_id=user_id, kind=kind, name="Entry", amount=amount, currency=currency,
            category=category, occurred_on=on or self.today,
        ))
        self.db.commit()

    def goal(self, name="Trip", target=1000, saved=None, archived=False) -> Goal:
        row = Goal(
            id=uuid4(), user_id="owner", name=name, target_amount=target, currency="AUD",
            archived_at=datetime(2026, 1, 1) if archived else None,
        )
        self.db.add(row)
        if saved is not None:
            self.db.add(GoalContribution(user_id="owner", goal_id=row.id, amount=saved, occurred_on=self.today))
        self.db.commit()
        return row

    def test_payment_list_converts_monthly_costs_and_reports_unconverted(self):
        self.payment("Netflix", 20)
        self.payment("Hulu", 10, currency="USD")
        self.payment("BBC", 5, currency="GBP")
        self.payment("Gym", 50, category=Category.health)
        self.payment("Theirs", 99, user_id="other")

        data = self.data({"type": "payment_list", "category": "streaming"})

        by_name = {row["name"]: row for row in data["payments"]}
        self.assertEqual(set(by_name), {"BBC", "Hulu", "Netflix"})
        self.assertEqual(by_name["Hulu"]["monthly_in_base"], 20.0)
        self.assertIsNone(by_name["BBC"]["monthly_in_base"])
        self.assertEqual(by_name["Netflix"]["cadence_label"], "Monthly")
        self.assertEqual(data["monthly_total_in_base"], 40.0)
        self.assertEqual(data["unconverted_count"], 1)
        self.assertEqual(data["currency_conversion"]["status"], "incomplete")

    def test_payment_list_by_ids_skips_and_counts_deleted_payments(self):
        kept = self.payment("Netflix", 20)
        self.payment("Hulu", 10)
        deleted = self.payment("Gone", 10)
        self.db.delete(deleted)
        self.db.commit()

        data = self.data({"type": "payment_list", "payment_ids": [str(kept.id), str(deleted.id)]})

        self.assertEqual([row["name"] for row in data["payments"]], ["Netflix"])
        self.assertEqual(data["missing_count"], 1)
        self.assertEqual(data["inactive_count"], 0)

    def test_payment_list_counts_listed_payments_that_are_no_longer_active(self):
        kept = self.payment("Netflix", 20)
        cancelled = self.payment("Old gym", 30)
        cancelled.is_active = False
        self.db.commit()

        data = self.data({"type": "payment_list", "payment_ids": [str(kept.id), str(cancelled.id)]})

        self.assertEqual([row["name"] for row in data["payments"]], ["Netflix"])
        self.assertEqual((data["inactive_count"], data["missing_count"]), (1, 0))

    def test_transaction_log_ranges_filters_and_totals(self):
        last_month = previous_month(self.today)
        self.entry(30)
        self.entry(10, currency="USD")
        self.entry(5, currency="GBP")
        self.entry(500, kind="income", category=Category.other)
        self.entry(40, on=last_month)
        self.entry(7, user_id="other")

        this_month = self.data({"type": "transaction_log"})
        summary = month_summary(self.db, "owner", self.today.year, self.today.month)
        self.assertEqual(this_month["entry_count"], 4)
        self.assertEqual((this_month["expenses"], this_month["income"]), (summary["expenses"], summary["income"]))
        self.assertEqual(this_month["expenses"], 50.0)
        self.assertEqual(this_month["unconverted_count"], 1)

        both = self.data({"type": "transaction_log", "range": "last_3_months", "kind": "expense"})
        self.assertEqual(both["entry_count"], 4)
        self.assertEqual(both["expenses"], 90.0)
        self.assertEqual(both["income"], 0.0)
        dates = [entry["occurred_on"] for entry in both["entries"]]
        self.assertEqual(dates, sorted(dates, reverse=True))

        previous = self.data({"type": "transaction_log", "range": "last_month"})
        self.assertEqual([entry["amount"] for entry in previous["entries"]], [40.0])

    def test_transaction_log_shows_at_most_one_hundred_entries(self):
        for _ in range(workspace_data.TRANSACTION_LOG_LIMIT + 5):
            self.db.add(Transaction(
                user_id="owner", kind="expense", name="Coffee", amount=1, currency="AUD",
                category=Category.food, occurred_on=self.today,
            ))
        self.db.commit()

        data = self.data({"type": "transaction_log"})

        self.assertEqual(len(data["entries"]), workspace_data.TRANSACTION_LOG_LIMIT)
        self.assertEqual(data["entry_count"], workspace_data.TRANSACTION_LOG_LIMIT + 5)
        self.assertEqual(data["expenses"], 105.0)

    def test_budget_matches_budget_status_for_chosen_categories(self):
        for category in (Category.food, Category.transport):
            self.db.add(Budget(user_id="owner", category=category, monthly_limit=100, currency="AUD"))
        self.db.commit()
        self.entry(30)

        data = self.data({"type": "budget", "categories": ["food"]})

        expected = budget_status(self.db, "owner", self.today.year, self.today.month)
        self.assertEqual(data["budgets"], [row for row in expected["budgets"] if row["category"] == "food"])
        self.assertEqual(data["budgets"][0]["left"], 70.0)

    def test_goal_progress_shows_active_goals_unless_listed(self):
        trip = self.goal("Trip", 1000, saved=250)
        old = self.goal("Old", 100, archived=True)
        deleted = self.goal("Gone")
        self.db.delete(deleted)
        self.db.commit()

        active = self.data({"type": "goal_progress"})
        listed = self.data({"type": "goal_progress", "goal_ids": [str(old.id), str(trip.id), str(deleted.id)]})

        endpoint = {goal["id"]: goal for goal in list_goals(include_archived=False, user_id="owner", db=self.db)}
        self.assertEqual([goal["name"] for goal in active["goals"]], ["Trip"])
        self.assertEqual(active["goals"][0]["percent"], endpoint[str(trip.id)]["percent"])
        self.assertEqual(active["goals"][0]["saved"], 250.0)
        self.assertNotIn("contributions", active["goals"][0])
        self.assertEqual({goal["name"] for goal in listed["goals"]}, {"Trip", "Old"})
        self.assertEqual(listed["missing_count"], 1)

    def test_upcoming_payments_match_the_forecast(self):
        self.payment("Netflix", 20, due_in_days=3)
        self.payment("Hulu", 10, currency="USD", due_in_days=4)
        self.payment("BBC", 5, currency="GBP", due_in_days=5)
        self.payment("Later", 99, due_in_days=20)

        data = self.data({"type": "upcoming_payments", "days": 14})

        forecast = get_upcoming_forecast(days=14, user_id="owner", db=self.db)
        self.assertEqual([charge["name"] for charge in data["charges"]], ["Netflix", "Hulu", "BBC"])
        self.assertEqual(data["total_in_base"], forecast["forecast_total_in_base"])
        self.assertEqual(data["total_in_base"], 40.0)
        self.assertEqual(data["unconverted_count"], 1)

    def test_spending_trend_lists_logged_and_tracked_spending_per_month(self):
        self.entry(30)
        self.entry(12, category=Category.transport)
        self.entry(5, currency="GBP", on=previous_month(self.today))
        self.payment("Delivery", 15, category=Category.food, due_in_days=0)

        data = self.data({"type": "spending_trend", "months": 3, "category": "food"})

        months = data["months"]
        self.assertEqual(len(months), 3)
        self.assertEqual(months[-1]["month"], f"{self.today.year:04d}-{self.today.month:02d}")
        self.assertEqual([row["month"] for row in months], sorted(row["month"] for row in months))
        self.assertEqual((months[-1]["logged_expenses"], months[-1]["tracked_payments"]), (30.0, 15.0))
        self.assertTrue(months[-2]["has_unconverted"])
        self.assertFalse(months[0]["has_unconverted"])

    def test_spending_trend_counts_a_linked_expense_once_like_budgets(self):
        bill = self.payment("Delivery", 15, category=Category.food, due_in_days=0)
        self.db.add(Transaction(
            user_id="owner", kind="expense", name="Delivery", amount=15, currency="AUD",
            category=Category.food, occurred_on=self.today, recurring_payment_id=bill.id,
        ))
        self.db.add(Budget(user_id="owner", category=Category.food, monthly_limit=100, currency="AUD"))
        self.db.commit()
        self.entry(30)

        month = self.data({"type": "spending_trend", "months": 3, "category": "food"})["months"][-1]

        spent = budget_status(self.db, "owner", self.today.year, self.today.month)["budgets"][0]["spent"]
        self.assertEqual((month["logged_expenses"], month["tracked_payments"]), (30.0, 15.0))
        self.assertEqual(month["logged_expenses"] + month["tracked_payments"], spent)

    def test_spending_trend_flags_only_unconverted_expenses_in_the_category(self):
        self.entry(5, kind="income", currency="GBP", category=Category.other)
        self.entry(5, currency="GBP", category=Category.transport)

        food = self.data({"type": "spending_trend", "months": 3, "category": "food"})["months"][-1]
        every = self.data({"type": "spending_trend", "months": 3})["months"][-1]

        self.assertEqual((food["logged_unconverted_count"], food["has_unconverted"]), (0, False))
        self.assertEqual(every["logged_unconverted_count"], 1)

    def test_shared_costs_balance_to_the_cent(self):
        data = self.data({
            "type": "shared_costs",
            "people": ["Ana", "Ben", "Cara"],
            "items": [
                {"label": "Dinner", "amount": "100.00", "paid_by": "Ana", "split_between": ["Ana", "Ben", "Cara"]},
                {"label": "Taxi", "amount": "20.00", "paid_by": "Ben", "split_between": ["Ben", "Cara"]},
            ],
        })

        people = {row["name"]: row for row in data["people"]}
        self.assertEqual(data["currency"], "AUD")
        self.assertEqual(data["total"], 120.0)
        self.assertEqual([people[name]["share"] for name in ("Ana", "Ben", "Cara")], [33.34, 43.33, 43.33])
        self.assertEqual((people["Ana"]["net"], people["Ana"]["status"]), (66.66, "is_owed"))
        self.assertEqual((people["Cara"]["net"], people["Cara"]["status"]), (-43.33, "owes"))
        self.assertAlmostEqual(sum(row["net"] for row in data["people"]), 0, places=9)
        self.assertAlmostEqual(sum(row["share"] for row in data["people"]), data["total"], places=9)

    def test_checklist_and_notes_echo_their_content(self):
        checklist, notes = self.resolve(
            {"type": "checklist", "title": "Pack", "items": [{"text": "Passport", "done": True}]},
            {"type": "notes", "text": "Hello"},
        )

        self.assertEqual(checklist, {
            "type": "checklist", "title": "Pack", "data": {"items": [{"text": "Passport", "done": True}]},
        })
        self.assertEqual(notes["data"], {"text": "Hello"})

    def test_a_failing_block_only_fails_itself(self):
        def broken(*_args):
            raise RuntimeError("boom")

        with patch.dict(workspace_data.RESOLVERS, {"budget": broken}), self.assertLogs(workspace_data.logger):
            budget, notes, stale = self.resolve(
                {"type": "budget", "title": "Food"},
                {"type": "notes", "text": "Still here"},
                {"type": "removed_type"},
            )

        self.assertEqual(budget, {"type": "budget", "title": "Food", "error": BLOCK_FAILED})
        self.assertEqual(notes["data"], {"text": "Still here"})
        self.assertEqual(stale["error"], BLOCK_FAILED)


class WorkspaceDataRouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def page_id(self, user_id: str) -> UUID:
        page = create_page(
            PageCreate(title="Trip", blocks=[{"type": "notes", "text": "Hi"}]), user_id=user_id, db=self.db,
        )
        return UUID(page["id"])

    def test_returns_each_block_in_order(self):
        page_id = self.page_id("owner")

        result = get_page_data(page_id, user_id="owner", db=self.db)

        self.assertEqual(result["title"], "Trip")
        self.assertEqual(result["blocks"], [{"type": "notes", "title": None, "data": {"text": "Hi"}}])

    def test_other_users_pages_return_404(self):
        theirs = self.page_id("other")

        with self.assertRaises(HTTPException) as caught:
            get_page_data(theirs, user_id="owner", db=self.db)
        self.assertEqual(caught.exception.status_code, 404)

    def test_refuses_when_workspace_is_off(self):
        page_id = self.page_id("owner")
        self.db.add(UserPreference(user_id="owner", base_currency="AUD", enabled_features=["spending"]))
        self.db.commit()

        with self.assertRaises(HTTPException) as caught:
            get_page_data(page_id, user_id="owner", db=self.db)
        self.assertEqual((caught.exception.status_code, caught.exception.detail), (403, WORKSPACE_OFF))


if __name__ == "__main__":
    unittest.main()
