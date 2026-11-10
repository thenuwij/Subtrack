import os
import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import SafeToSpendProfile, SetAside, Transaction, UserPreference  # noqa: E402
from app.services.pay_cycles import pay_cycles  # noqa: E402

# 3 Nov in Sydney. This cycle: 27 Oct to 10 Nov; the one before: 13 Oct to 27 Oct.
NOW = datetime(2026, 11, 3, 2, 0)
RATES = {"rates": {}, "stale": False, "fetched_at": "2026-11-03T00:00:00"}


class PayCycleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        patcher = patch("app.services.set_asides.get_cached_rate_snapshot", return_value=RATES)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.db.add(UserPreference(user_id="owner", base_currency="AUD", timezone="Australia/Sydney"))
        self.db.add(SafeToSpendProfile(
            user_id="owner", balance=None, balance_as_of=None, pay_amount=Decimal("1400"), currency="AUD",
            pay_anchor_on=date(2026, 11, 10), pay_interval_unit="week", pay_interval_count=2, buffer=Decimal("50"),
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def set_aside(self, kind, name, amount, added=datetime(2026, 10, 1)):
        row = SetAside(id=uuid4(), user_id="owner", kind=kind, name=name, amount_per_pay=amount, currency="AUD", created_at=added)
        self.db.add(row)
        self.db.commit()
        return row

    def spend(self, amount, on, pot=None, name="Spend"):
        self.db.add(Transaction(
            user_id="owner", kind="expense", name=name, amount=amount, currency="AUD",
            occurred_on=on, set_aside_id=pot.id if pot else None,
        ))
        self.db.commit()

    def cycles(self, count=1):
        return pay_cycles(self.db, "owner", count=count, now=NOW)["cycles"]

    def test_cycles_run_from_payday_to_payday_newest_first(self):
        cycles = self.cycles(count=2)

        self.assertEqual(
            [(c["start"], c["end"], c["current"]) for c in cycles],
            [("2026-10-27", "2026-11-10", True), ("2026-10-13", "2026-10-27", False), ("2026-09-29", "2026-10-13", False)],
        )

    def test_each_cycle_shows_pots_planned_against_spent_and_other_spends(self):
        pot = self.set_aside("pot", "Eating out", 60)
        self.set_aside("save", "Trip", 100)
        self.spend(20, date(2026, 11, 2), pot)
        self.spend(70, date(2026, 10, 20), pot)
        self.spend(30, date(2026, 10, 21))

        current, previous = self.cycles()

        self.assertEqual(current["pots"][0], {"id": str(pot.id), "name": "Eating out", "planned": 60.0, "spent": 20.0, "left": 40.0, "over": 0.0})
        self.assertEqual((previous["pots"][0]["over"], previous["other_spent"], previous["saved"]), (10.0, 30.0, 100.0))
        self.assertEqual([s["pot"] for s in previous["spends"]], [None, "Eating out"])

    def test_a_pot_added_later_is_not_in_earlier_cycles(self):
        self.set_aside("pot", "Fuel", 40, added=datetime(2026, 11, 1))

        current, previous = self.cycles()

        self.assertEqual(([p["name"] for p in current["pots"]], previous["pots"]), (["Fuel"], []))

    def test_no_pay_details_means_no_cycles(self):
        self.db.delete(self.db.get(SafeToSpendProfile, "owner"))
        self.db.commit()

        self.assertEqual(pay_cycles(self.db, "owner", now=NOW)["cycles"], [])


if __name__ == "__main__":
    unittest.main()
