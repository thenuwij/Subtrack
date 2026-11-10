import os
import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import SafeToSpendProfile, SetAside, Transaction, UserPreference  # noqa: E402
from app.routers.set_asides import (  # noqa: E402
    IncomeCreate,
    SetAsideCreate,
    SpendCreate,
    SpendUpdate,
    create_set_aside,
    delete_set_aside,
    edit_spend,
    log_income,
    log_spend,
    undo_spend,
)
from app.services.safe_to_spend import safe_to_spend  # noqa: E402

# 3 Nov in Sydney; pay cycle 27 Oct to 10 Nov. Pay A$1,400, buffer A$50, no bills.
NOW = datetime(2026, 11, 3, 2, 0)
RATES = {"rates": {}, "stale": False, "fetched_at": "2026-11-03T00:00:00"}


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.replace(hour=13).replace(tzinfo=tz)  # 1pm on 3 Nov, local


class SetAsideTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        for target in ("app.agent.finance.get_cached_rate_snapshot", "app.services.set_asides.get_cached_rate_snapshot"):
            patcher = patch(target, return_value=RATES)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.db.add(UserPreference(user_id="owner", base_currency="AUD", timezone="Australia/Sydney"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def profile(self, **overrides):
        values = {
            "user_id": "owner", "balance": None, "balance_as_of": None, "pay_amount": Decimal("1400.00"),
            "currency": "AUD", "pay_anchor_on": date(2026, 11, 10), "pay_interval_unit": "week",
            "pay_interval_count": 2, "buffer": Decimal("50.00"),
        }
        self.db.add(SafeToSpendProfile(**{**values, **overrides}))
        self.db.commit()

    def set_aside(self, kind, name, amount, **fields):
        row = SetAside(id=uuid4(), user_id="owner", kind=kind, name=name, amount_per_pay=amount, currency="AUD", **fields)
        self.db.add(row)
        self.db.commit()
        return row

    def spend(self, amount, *, pot=None, on=date(2026, 11, 2), created_at=datetime(2026, 11, 2, 1, 0)):
        self.db.add(Transaction(
            user_id="owner", kind="expense", name="Spend", amount=amount, currency="AUD",
            occurred_on=on, created_at=created_at, set_aside_id=pot.id if pot else None,
        ))
        self.db.commit()

    def position(self):
        return safe_to_spend(self.db, "owner", now=NOW)

    def test_savings_and_pots_come_off_each_pay(self):
        self.profile()
        self.set_aside("save", "Trip", 100, target_amount=1000)
        self.set_aside("pot", "Eating out", 60)

        result = self.position()

        self.assertEqual((result["set_aside"], result["spent"], result["safe_to_spend"]), (160.0, 0.0, 1190.0))
        self.assertEqual(
            sorted((s["name"], s.get("left")) for s in result["set_asides"]),
            [("Eating out", 60.0), ("Trip", None)],
        )

    def test_a_spend_from_a_pot_leaves_free_money_unchanged(self):
        self.profile()
        pot = self.set_aside("pot", "Eating out", 60)
        self.spend(20, pot=pot)

        result = self.position()

        self.assertEqual(result["set_asides"][0]["left"], 40.0)
        self.assertEqual(result["safe_to_spend"], 1290.0)  # 1400 - 50 - 40 left - 20 spent

    def test_overspending_a_pot_comes_out_of_free_money(self):
        self.profile()
        pot = self.set_aside("pot", "Eating out", 60)
        self.spend(80, pot=pot)

        self.assertEqual(self.position()["safe_to_spend"], 1270.0)  # 20 over the pot

    def test_other_spends_lower_free_money(self):
        self.profile()
        self.spend(200)

        self.assertEqual(self.position()["safe_to_spend"], 1150.0)

    def test_spends_from_an_earlier_pay_cycle_do_not_count(self):
        self.profile()
        pot = self.set_aside("pot", "Eating out", 60)
        self.spend(50, pot=pot, on=date(2026, 10, 26))

        result = self.position()

        self.assertEqual((result["set_asides"][0]["left"], result["safe_to_spend"]), (60.0, 1290.0))

    def test_a_balance_already_shows_spends_logged_before_it(self):
        self.profile(balance=Decimal("500.00"), balance_as_of=datetime(2026, 11, 2, 12, 0))
        pot = self.set_aside("pot", "Eating out", 60)
        self.spend(20, pot=pot, created_at=datetime(2026, 11, 2, 1, 0))  # before the balance
        self.spend(30, created_at=datetime(2026, 11, 3, 1, 0))  # after it

        result = self.position()

        self.assertEqual(result["mode"], "balance")
        self.assertEqual(result["spent"], 30.0)
        self.assertEqual(result["safe_to_spend"], 380.0)  # 500 - 50 - 40 left - 30

    def test_bill_payments_are_not_counted_as_spends(self):
        self.profile()
        self.db.add(Transaction(
            user_id="owner", kind="expense", name="Phone", amount=35, currency="AUD",
            occurred_on=date(2026, 11, 2), recurring_payment_id=uuid4(),
        ))
        self.db.commit()

        self.assertEqual(self.position()["spent"], 0.0)

    def test_pay_plan_takes_off_spends_outside_budgets_and_over_them(self):
        self.profile(balance=Decimal("500.00"), balance_as_of=datetime(2026, 11, 2, 12, 0))
        pot = self.set_aside("pot", "Groceries", 150)
        self.spend(100, pot=pot)  # inside the budget: already held back
        self.spend(70, pot=pot)  # 20 over the budget
        self.spend(30, created_at=datetime(2026, 11, 3, 1, 0))  # outside any budget

        plan = self.position()["pay_plan"]

        # Spends before the balance still count here: the plan works from pay, not the balance.
        self.assertEqual((plan["set_aside"], plan["spent"]), (150.0, 50.0))
        self.assertEqual(plan["left"], 1200.0)  # 1400 - 150 - 50
        self.assertEqual(plan["over_budgets"], 20.0)
        self.assertEqual(plan["spent_by_category"], [{"category": "other", "amount": 30.0}])

    def income(self, amount, *, on=date(2026, 11, 2), created_at=datetime(2026, 11, 2, 1, 0)):
        self.db.add(Transaction(
            user_id="owner", kind="income", name="Extra shift", amount=amount, currency="AUD",
            occurred_on=on, created_at=created_at,
        ))
        self.db.commit()

    def test_extra_income_adds_to_this_pay_and_to_free_money(self):
        self.profile()
        self.income(200)

        result = self.position()

        self.assertEqual((result["extra_income"], result["safe_to_spend"]), (200.0, 1550.0))
        plan = result["pay_plan"]
        self.assertEqual((plan["extra_income"], plan["left"]), (200.0, 1600.0))
        self.assertEqual(plan["incomes"][0]["name"], "Extra shift")

    def test_a_balance_already_shows_income_logged_before_it(self):
        self.profile(balance=Decimal("500.00"), balance_as_of=datetime(2026, 11, 2, 12, 0))
        self.income(100, created_at=datetime(2026, 11, 2, 1, 0))  # before the balance
        self.income(40, created_at=datetime(2026, 11, 3, 1, 0))  # after it

        result = self.position()

        self.assertEqual(result["safe_to_spend"], 490.0)  # 500 - 50 buffer + 40
        self.assertEqual(result["pay_plan"]["extra_income"], 140.0)

    def test_income_from_an_earlier_pay_cycle_does_not_count(self):
        self.profile()
        self.income(200, on=date(2026, 10, 26))

        result = self.position()

        self.assertEqual((result["extra_income"], result["pay_plan"]["extra_income"]), (0.0, 0.0))


class SetAsideApiTests(SetAsideTests):
    def test_editing_a_spend_fixes_its_amount_category_and_budget(self):
        self.profile()
        pot = self.set_aside("pot", "Groceries", 150)

        with (
            patch("app.routers.set_asides.datetime", FixedClock),
            patch("app.routers.set_asides.safe_to_spend", side_effect=lambda db, user_id: safe_to_spend(db, user_id, now=NOW)),
        ):
            logged = log_spend(SpendCreate(name="Coles", amount=Decimal("80")), user_id="owner", db=self.db)
            spend_id = UUID(logged["spends"][0]["id"])
            edited = edit_spend(
                spend_id, SpendUpdate(amount=Decimal("60"), category="food", set_aside_id=pot.id), user_id="owner", db=self.db,
            )
            moved_out = edit_spend(spend_id, SpendUpdate(set_aside_id=None), user_id="owner", db=self.db)

        self.assertEqual(logged["pay_plan"]["spent"], 80.0)
        self.assertEqual(edited["spends"][0]["amount"], 60.0)
        self.assertEqual(edited["spends"][0]["category"], "food")
        self.assertEqual((edited["set_asides"][0]["left"], edited["pay_plan"]["spent"]), (90.0, 0.0))
        self.assertEqual(moved_out["pay_plan"]["spent_by_category"], [{"category": "food", "amount": 60.0}])

    def test_editing_extra_income_only_changes_name_and_amount(self):
        self.profile()
        self.income(100)
        income_id = UUID(self.position()["incomes"][0]["id"])

        with patch("app.routers.set_asides.safe_to_spend", side_effect=lambda db, user_id: safe_to_spend(db, user_id, now=NOW)):
            edited = edit_spend(income_id, SpendUpdate(amount=Decimal("150")), user_id="owner", db=self.db)
            with self.assertRaises(HTTPException) as caught:
                edit_spend(income_id, SpendUpdate(category="food"), user_id="owner", db=self.db)

        self.assertEqual(edited["pay_plan"]["extra_income"], 150.0)
        self.assertEqual(caught.exception.status_code, 422)

    def test_you_can_only_edit_your_own_spends(self):
        self.profile()
        self.db.add(Transaction(
            user_id="someone-else", kind="expense", name="Theirs", amount=10, currency="AUD", occurred_on=date(2026, 11, 2),
        ))
        self.db.commit()
        theirs = self.db.query(Transaction).filter(Transaction.user_id == "someone-else").one()

        with self.assertRaises(HTTPException) as caught:
            edit_spend(theirs.id, SpendUpdate(amount=Decimal("1")), user_id="owner", db=self.db)

        self.assertEqual(caught.exception.status_code, 404)

    def test_a_spend_keeps_its_category_and_cannot_be_income(self):
        self.profile()

        with (
            patch("app.routers.set_asides.datetime", FixedClock),
            patch("app.routers.set_asides.safe_to_spend", side_effect=lambda db, user_id: safe_to_spend(db, user_id, now=NOW)),
        ):
            after = log_spend(SpendCreate(name="Uber", amount=Decimal("18"), category="transport"), user_id="owner", db=self.db)
            with self.assertRaises(HTTPException) as caught:
                log_spend(SpendCreate(name="Oops", amount=Decimal("5"), category="income"), user_id="owner", db=self.db)

        self.assertEqual(after["spends"][0]["category"], "transport")
        self.assertEqual(after["pay_plan"]["spent_by_category"], [{"category": "transport", "amount": 18.0}])
        self.assertEqual(caught.exception.status_code, 422)

    def test_logging_income_returns_the_new_number_and_undo_restores_it(self):
        self.profile()

        with (
            patch("app.routers.set_asides.datetime", FixedClock),
            patch("app.routers.set_asides.safe_to_spend", side_effect=lambda db, user_id: safe_to_spend(db, user_id, now=NOW)),
        ):
            after = log_income(IncomeCreate(name="Extra shift", amount=Decimal("120")), user_id="owner", db=self.db)
            income_id = after["incomes"][0]["id"]
            undone = undo_spend(UUID(income_id), user_id="owner", db=self.db)

        self.assertEqual(after["pay_plan"]["left"], 1520.0)
        self.assertEqual(undone["pay_plan"]["left"], 1400.0)

    def test_logging_a_spend_returns_the_new_number_and_undo_restores_it(self):
        self.profile()
        pot = self.set_aside("pot", "Eating out", 60)

        with (
            patch("app.routers.set_asides.datetime", FixedClock),
            patch("app.routers.set_asides.safe_to_spend", side_effect=lambda db, user_id: safe_to_spend(db, user_id, now=NOW)),
        ):
            after = log_spend(SpendCreate(name="Dinner", amount=Decimal("25"), set_aside_id=pot.id), user_id="owner", db=self.db)
            spend_id = after["spends"][0]["id"]
            undone = undo_spend(UUID(spend_id), user_id="owner", db=self.db)

        self.assertEqual(after["set_asides"][0]["left"], 35.0)
        self.assertEqual(undone["set_asides"][0]["left"], 60.0)

    def test_spends_only_come_out_of_your_own_pots(self):
        self.profile()
        saving = self.set_aside("save", "Trip", 100)
        theirs = SetAside(id=uuid4(), user_id="other", kind="pot", name="Theirs", amount_per_pay=10, currency="AUD")
        self.db.add(theirs)
        self.db.commit()

        for target, status in ((saving.id, 422), (theirs.id, 404)):
            with self.subTest(status=status), self.assertRaises(HTTPException) as caught:
                log_spend(SpendCreate(name="X", amount=Decimal("5"), set_aside_id=target), user_id="owner", db=self.db)
            self.assertEqual(caught.exception.status_code, status)

    def test_a_pot_ignores_targets_and_deleting_it_keeps_the_spend(self):
        pot = create_set_aside(
            SetAsideCreate(kind="pot", name="Eating out", amount_per_pay=Decimal("60"), target_amount=Decimal("500")),
            user_id="owner", db=self.db,
        )
        self.assertIsNone(pot["target_amount"])
        self.spend(10, pot=self.db.get(SetAside, UUID(pot["id"])))

        delete_set_aside(UUID(pot["id"]), user_id="owner", db=self.db)

        spend = self.db.query(Transaction).one()
        self.assertIsNone(spend.set_aside_id)


if __name__ == "__main__":
    unittest.main()
