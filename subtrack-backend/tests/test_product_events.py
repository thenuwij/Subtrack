import os
import unittest
from datetime import datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.models import ProductEvent, ReminderDelivery  # noqa: E402
from app.routers.events import EventIn  # noqa: E402
from app.services.product_events import actor_for, product_summary, record  # noqa: E402

START = datetime(2026, 11, 1, 9, 0)


class ProductEventTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def names(self):
        return sorted(event.name for event in self.db.query(ProductEvent))

    def test_events_hold_only_a_hashed_actor_name_and_time(self):
        record(self.db, "user-1", "afford_check", now=START)

        event = self.db.query(ProductEvent).one()
        self.assertEqual(event.actor, actor_for("user-1"))
        self.assertNotIn("user-1", event.actor)
        self.assertEqual(len(event.actor), 64)

    def test_once_per_user_and_once_per_day_events_are_not_repeated(self):
        for _ in range(2):
            record(self.db, "u", "setup_started", now=START)
            record(self.db, "u", "home_viewed", now=START)
        record(self.db, "u", "home_viewed", now=START + timedelta(days=1))
        record(self.db, "u", "afford_check", now=START)
        record(self.db, "u", "afford_check", now=START)

        self.assertEqual(self.names(), ["afford_check", "afford_check", "home_viewed", "home_viewed", "setup_started"])

    def test_demo_accounts_and_unknown_events_are_ignored(self):
        record(self.db, "demo_abc", "home_viewed", now=START)
        record(self.db, "u", "made_up", now=START)

        self.assertEqual(self.names(), [])

    def test_the_browser_can_only_send_its_own_events(self):
        EventIn(name="setup_started")
        with self.assertRaises(ValidationError):
            EventIn(name="balance_updated")

    def test_summary_reports_setup_speed_and_second_cycle_retention(self):
        # Fast: 2 minutes, came back on day 20. Slow: 5 minutes, never came back. Quitter: never finished.
        for user, minutes in (("fast", 2), ("slow", 5)):
            record(self.db, user, "setup_started", now=START)
            record(self.db, user, "setup_finished", now=START + timedelta(minutes=minutes))
        record(self.db, "quitter", "setup_started", now=START)
        record(self.db, "fast", "home_viewed", now=START + timedelta(days=20))
        self.db.add(ReminderDelivery(key="payday/fast/2026-11-10", user_id="fast", payload={}, created_at=START, sent_at=START))
        self.db.commit()
        record(self.db, "fast", "payday_link_clicked", now=START + timedelta(days=9))

        summary = product_summary(self.db, START - timedelta(days=1), now=START + timedelta(days=30))

        self.assertEqual(summary["setup"], {
            "started": 3, "finished": 2, "completion_rate": 0.667, "median_minutes": 3.5, "under_3_minutes_rate": 0.5,
        })
        self.assertEqual(summary["retention"], {"cohort": 2, "returned_in_second_cycle": 1, "rate": 0.5})
        self.assertEqual(summary["payday_emails"], {"sent": 1, "links_clicked": 1, "click_rate": 1.0})


if __name__ == "__main__":
    unittest.main()
