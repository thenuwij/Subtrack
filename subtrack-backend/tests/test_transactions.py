import os
import re
import unittest
from datetime import date, datetime
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import BillingCycle, Category, Subscription, Transaction, TransactionKind, UserPreference  # noqa: E402
from app.routers.budgets import BudgetCreate, create_budget  # noqa: E402
from app.routers.transactions import (  # noqa: E402
    MONTH_PATTERN,
    TransactionCreate,
    TransactionUpdate,
    create_transaction,
    delete_transaction,
    get_transaction_summary,
    list_transactions,
    update_transaction,
)
from app.services.budgets import budget_status  # noqa: E402

# One AUD buys 0.5 USD, so 10 USD is 20 AUD.
RATES = {"base": "AUD", "rates": {"USD": 0.5}, "stale": False, "fetched_at": "2026-11-03T00:00:00"}


class TransactionApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(UserPreference(user_id="owner", base_currency="AUD", timezone="Australia/Sydney"))
        self.db.commit()
        self.use_rates(RATES)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def use_rates(self, snapshot):
        for target in (
            "app.routers.rates.get_cached_rate_snapshot",
            "app.services.transactions.get_cached_rate_snapshot",
        ):
            patcher = patch(target, return_value=snapshot)
            patcher.start()
            self.addCleanup(patcher.stop)

    def create(self, user_id="owner", **fields):
        body = {
            "kind": "expense", "name": "Woolworths", "amount": "42.10",
            "currency": "AUD", "category": "food", "occurred_on": "2026-11-10",
            **fields,
        }
        return create_transaction(TransactionCreate(**body), user_id=user_id, db=self.db)

    def add_payment(self, user_id="owner"):
        payment = Subscription(
            user_id=user_id, name="AGL Energy", category=Category.utilities,
            amount=180.0, currency="AUD", cycle=BillingCycle.monthly,
            interval_unit="month", interval_count=1, is_active=True,
        )
        self.db.add(payment)
        self.db.commit()
        return payment

    def test_base_currency_expense_stores_its_own_amount(self):
        created = self.create()

        self.assertEqual(created["base_amount"], 42.10)
        self.assertEqual(created["base_currency"], "AUD")
        self.assertEqual(created["source"], "manual")
        self.assertIsNone(created["rate_as_of"])

    def test_foreign_expense_is_converted_with_the_shared_snapshot(self):
        created = self.create(amount="10.00", currency="USD")

        self.assertEqual(created["base_amount"], 20.0)
        self.assertEqual(created["rate_as_of"], "2026-11-03T00:00:00")

    def test_foreign_expense_without_a_rate_is_unconverted_and_left_out_of_totals(self):
        self.use_rates(None)
        self.create(amount="50.00")
        created = self.create(name="Amazon", amount="10.00", currency="USD")

        summary = get_transaction_summary(month="2026-11", user_id="owner", db=self.db)

        self.assertIsNone(created["base_amount"])
        self.assertIsNone(created["base_currency"])
        self.assertEqual(summary["expenses"], 50.0)
        self.assertEqual(summary["unconverted_count"], 1)

    def test_client_cannot_send_source_or_base_amount(self):
        base = {"kind": "expense", "name": "Coffee", "amount": "5", "currency": "AUD"}
        for extra in ({"source": "email"}, {"base_amount": "1.00"}):
            with self.assertRaises(ValidationError):
                TransactionCreate(**base, **extra)
            with self.assertRaises(ValidationError):
                TransactionUpdate(**extra)

    def test_amount_must_be_positive_bounded_and_in_cents(self):
        base = {"kind": "expense", "name": "Coffee", "currency": "AUD"}
        for amount in ("0", "-1", "1.234", "1000000.01", "NaN"):
            with self.assertRaises(ValidationError):
                TransactionCreate(**base, amount=amount)

    def test_unsupported_currency_is_rejected(self):
        with self.assertRaises(ValidationError):
            TransactionCreate(kind="expense", name="Coffee", amount="5", currency="NZD")

    def test_dates_and_months_outside_2000_to_2100_are_rejected(self):
        for day in (date(1999, 12, 31), date(2101, 1, 1)):
            with self.assertRaises(ValidationError):
                TransactionCreate(kind="expense", name="Coffee", amount="5", currency="AUD", occurred_on=day)
        self.assertIsNone(re.match(MONTH_PATTERN, "0000-01"))
        self.assertIsNotNone(re.match(MONTH_PATTERN, "2026-11"))

    def test_required_fields_cannot_be_cleared_on_edit(self):
        with self.assertRaises(ValidationError):
            TransactionUpdate(name=None)
        self.assertIsNone(TransactionUpdate(note=None).note)

    def test_occurred_on_defaults_to_today_in_the_users_timezone(self):
        with patch("app.routers.transactions.datetime") as fake_datetime:
            fake_datetime.now.return_value.date.return_value = date(2026, 11, 11)
            created = create_transaction(
                TransactionCreate(kind="expense", name="Coffee", amount="5", currency="AUD"),
                user_id="owner", db=self.db,
            )

        self.assertEqual(created["occurred_on"], "2026-11-11")
        self.assertEqual(str(fake_datetime.now.call_args.args[0]), "Australia/Sydney")

    def test_other_users_rows_cannot_be_read_edited_or_deleted(self):
        row_id = UUID(self.create()["id"])

        self.assertEqual(list_transactions(month="2026-11", user_id="intruder", db=self.db), [])
        with self.assertRaises(HTTPException) as edit:
            update_transaction(row_id, TransactionUpdate(name="Mine"), user_id="intruder", db=self.db)
        with self.assertRaises(HTTPException) as delete:
            delete_transaction(row_id, user_id="intruder", db=self.db)

        self.assertEqual((edit.exception.status_code, delete.exception.status_code), (404, 404))
        self.assertEqual(self.db.get(Transaction, row_id).name, "Woolworths")

    def test_another_users_payment_cannot_be_linked(self):
        foreign_payment = self.add_payment(user_id="other")
        created = self.create()

        with self.assertRaises(HTTPException) as on_create:
            self.create(recurring_payment_id=str(foreign_payment.id))
        with self.assertRaises(HTTPException) as on_edit:
            update_transaction(
                UUID(created["id"]), TransactionUpdate(recurring_payment_id=foreign_payment.id),
                user_id="owner", db=self.db,
            )

        self.assertEqual((on_create.exception.status_code, on_edit.exception.status_code), (404, 404))

    def test_own_payment_can_be_linked_and_unlinked(self):
        payment = self.add_payment()
        created = self.create(recurring_payment_id=str(payment.id))

        unlinked = update_transaction(
            UUID(created["id"]), TransactionUpdate(recurring_payment_id=None), user_id="owner", db=self.db,
        )

        self.assertEqual(created["recurring_payment_id"], str(payment.id))
        self.assertIsNone(unlinked["recurring_payment_id"])

    def test_editing_amount_or_currency_recomputes_the_conversion(self):
        created = self.create(amount="10.00")

        edited = update_transaction(
            UUID(created["id"]), TransactionUpdate(currency="USD"), user_id="owner", db=self.db,
        )

        self.assertEqual(edited["base_amount"], 20.0)
        self.assertEqual(edited["base_currency"], "AUD")

    def test_delete_removes_the_owners_row(self):
        created = self.create()

        delete_transaction(UUID(created["id"]), user_id="owner", db=self.db)

        self.assertEqual(list_transactions(month="2026-11", user_id="owner", db=self.db), [])

    def test_list_returns_the_month_newest_first_with_filters(self):
        self.create(name="Older", occurred_on="2026-11-02")
        self.create(name="Newer", occurred_on="2026-11-20", category="transport")
        self.create(name="Pay", kind="income", amount="2000", category="other")
        self.create(name="Last month", occurred_on="2026-10-31")

        rows = list_transactions(month="2026-11", user_id="owner", db=self.db)
        transport = list_transactions(
            month="2026-11", category=Category.transport, user_id="owner", db=self.db,
        )

        self.assertEqual([row["name"] for row in rows], ["Newer", "Pay", "Older"])
        self.assertEqual([row["name"] for row in transport], ["Newer"])

    def test_summary_totals_a_mixed_month(self):
        self.create(name="Pay", kind="income", amount="3000.00", category="other")
        self.create(name="Woolworths", amount="120.50", category="food")
        self.create(name="Cafe", amount="9.50", category="food", occurred_on="2026-11-03")
        self.create(name="Uber", amount="15.00", currency="USD", category="transport")
        self.create(name="October rent", amount="999.00", category="housing", occurred_on="2026-10-30")
        self.create(user_id="other", name="Someone else", amount="77.00")

        summary = get_transaction_summary(month="2026-11", user_id="owner", db=self.db)

        self.assertEqual(summary["income"], 3000.0)
        self.assertEqual(summary["expenses"], 160.0)
        self.assertEqual(summary["net"], 2840.0)
        self.assertEqual(summary["expenses_by_category"], {"food": 130.0, "transport": 30.0})
        self.assertEqual(summary["unconverted_count"], 0)
        self.assertEqual(summary["base_currency"], "AUD")
        self.assertEqual(summary["rate_as_of"], "2026-11-03T00:00:00")

    def test_summary_reexpresses_rows_stored_under_an_old_base_currency(self):
        self.create(amount="40.00")
        self.db.query(UserPreference).filter_by(user_id="owner").update({"base_currency": "USD"})
        self.db.commit()
        self.use_rates({**RATES, "base": "USD", "rates": {"AUD": 2.0}})

        summary = get_transaction_summary(month="2026-11", user_id="owner", db=self.db)

        self.assertEqual(summary["base_currency"], "USD")
        self.assertEqual(summary["expenses"], 20.0)

    def test_old_base_rows_without_a_current_rate_are_unconverted(self):
        self.create(amount="40.00")
        self.db.query(UserPreference).filter_by(user_id="owner").update({"base_currency": "USD"})
        self.db.commit()
        self.use_rates(None)

        summary = get_transaction_summary(month="2026-11", user_id="owner", db=self.db)

        self.assertEqual(summary["expenses"], 0.0)
        self.assertEqual(summary["unconverted_count"], 1)

    def test_similar_entry_is_returned_as_a_possible_duplicate(self):
        first = self.create()

        second = self.create(name="WOOLWORTHS 1234", amount="42.00", occurred_on="2026-11-11")

        self.assertEqual(
            [(match["kind"], match["id"]) for match in second["possible_duplicates"]],
            [("transaction", first["id"])],
        )
        self.assertEqual(len(list_transactions(month="2026-11", user_id="owner", db=self.db)), 2)


class PaymentChargesInTransactionsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(UserPreference(user_id="owner", base_currency="AUD", timezone="Australia/Sydney"))
        self.db.commit()
        for target in (
            "app.routers.rates.get_cached_rate_snapshot",
            "app.services.transactions.get_cached_rate_snapshot",
            "app.services.budgets.get_cached_rate_snapshot",
            "app.agent.finance.get_cached_rate_snapshot",
        ):
            patcher = patch(target, return_value=RATES)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def payment(self, name="Netflix", amount=22.0, currency="AUD", category=Category.streaming):
        row = Subscription(
            id=uuid4(), user_id="owner", name=name, category=category,
            amount=amount, currency=currency, cycle=BillingCycle.monthly,
            interval_unit="month", interval_count=1, is_active=True,
            next_due=datetime(2026, 11, 15),
        )
        self.db.add(row)
        self.db.commit()
        return row

    def expense(self, amount, category=Category.food, payment=None, kind="expense", day=10):
        self.db.add(Transaction(
            user_id="owner", kind=kind, name="Spend", amount=amount, currency="AUD",
            base_amount=amount, base_currency="AUD", category=category,
            occurred_on=date(2026, 11, day), recurring_payment_id=payment.id if payment else None,
        ))
        self.db.commit()

    def rows(self, **filters):
        return list_transactions(month="2026-11", user_id="owner", db=self.db, **filters)

    def summary(self):
        return get_transaction_summary(month="2026-11", user_id="owner", db=self.db)

    def test_charge_is_listed_as_a_read_only_recurring_row(self):
        netflix = self.payment()
        self.expense("5.00", day=20)

        rows = self.rows(kind=None, category=None)

        self.assertEqual([row["occurred_on"] for row in rows], ["2026-11-20", "2026-11-15"])
        charge = rows[1]
        self.assertEqual(charge["id"], f"payment:{netflix.id}:2026-11-15")
        self.assertEqual(charge["name"], "Netflix")
        self.assertEqual(charge["source"], "payment")
        self.assertTrue(charge["read_only"])
        self.assertEqual(charge["recurring_payment_id"], str(netflix.id))
        self.assertEqual(charge["base_amount"], 22.0)
        self.assertFalse(rows[0]["read_only"])

    def test_summary_adds_charges_and_matches_budgets(self):
        self.payment()
        self.expense("30.00")
        create_budget(BudgetCreate(category="food", monthly_limit="100.00"), user_id="owner", db=self.db)
        create_budget(BudgetCreate(category="streaming", monthly_limit="100.00"), user_id="owner", db=self.db)

        summary = self.summary()
        budgets = budget_status(self.db, "owner", 2026, 11)["budgets"]

        self.assertEqual(summary["expenses"], 52.0)
        self.assertEqual(summary["expenses_by_category"], {"food": 30.0, "streaming": 22.0})
        self.assertEqual(summary["payment_charge_count"], 1)
        self.assertEqual(sum(row["spent"] for row in budgets), summary["expenses"])

    def test_linked_expense_is_flagged_and_counted_once(self):
        netflix = self.payment()
        self.expense("22.00", category=Category.streaming, payment=netflix)

        logged = next(row for row in self.rows(kind=None, category=None) if row["source"] != "payment")

        self.assertTrue(logged["counted_in_payment"])
        self.assertEqual(self.summary()["expenses"], 22.0)

    def test_charge_without_a_rate_is_unconverted_not_one_to_one(self):
        self.payment(name="BBC", amount=10.0, currency="GBP")

        summary = self.summary()
        charge = self.rows(kind=None, category=None)[0]

        self.assertEqual(summary["expenses"], 0.0)
        self.assertEqual(summary["unconverted_count"], 1)
        self.assertIsNone(charge["base_amount"])
        self.assertIsNone(charge["base_currency"])

    def test_filters_apply_to_charges(self):
        self.payment()
        self.payment(name="AGL Energy", amount=180.0, category=Category.utilities)
        self.expense("1000.00", kind="income", category=Category.other)

        income = self.rows(kind=TransactionKind.income, category=None)
        utilities = self.rows(kind=None, category=Category.utilities)

        self.assertEqual([row["source"] for row in income], ["manual"])
        self.assertEqual([row["name"] for row in utilities], ["AGL Energy"])


if __name__ == "__main__":
    unittest.main()
