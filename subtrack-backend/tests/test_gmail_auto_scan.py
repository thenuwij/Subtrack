import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base  # noqa: E402
from app.gmail.analyzer import AnalysisOutcome  # noqa: E402
from app.gmail.scanner import SEARCH_QUERY, ScanResult  # noqa: E402
from app.models import GmailAccount, GmailReceipt  # noqa: E402
from app.routers import gmail as gmail_router  # noqa: E402


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AutoScanTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    def add_account(self, user_id="owner", **overrides):
        db = self.Session()
        values = {
            "user_id": user_id,
            "email_address": f"{user_id}@example.com",
            "refresh_token_encrypted": "encrypted",
            "scan_status": "done",
        }
        db.add(GmailAccount(**{**values, **overrides}))
        db.commit()
        db.close()

    def run_scan(self, run_id, *, partial=False, scan_error=None):
        """Run one scan with Gmail and the model stubbed; return the cursor passed in."""
        scan_result = ScanResult([], 0, 0, 0, partial)
        outcome = AnalysisOutcome([], 0, 0, 0, 0, False, False)
        scan_mock = patch("app.gmail.scanner.scan", return_value=scan_result) if scan_error is None \
            else patch("app.gmail.scanner.scan", side_effect=scan_error)
        with patch.object(gmail_router, "SessionLocal", self.Session), patch.object(
            gmail_router, "decrypt_token", return_value="token"
        ), scan_mock as scan, patch(
            "app.gmail.analyzer.analyze_bounded", return_value=outcome
        ), patch("app.gmail.analyzer.find_similar", return_value={}):
            if scan_error is None:
                gmail_router._run_scan("owner", run_id)
            else:
                with self.assertLogs("app.routers.gmail", level="ERROR"):
                    gmail_router._run_scan("owner", run_id)
        return scan.call_args.kwargs.get("after")

    def start_running(self, run_id, started_at, cursor=None):
        self.add_account(
            scan_status="running", scan_run_id=run_id,
            scan_started_at=started_at, scan_heartbeat_at=started_at, scan_cursor_at=cursor,
        )

    def cursor(self):
        db = self.Session()
        value = db.get(GmailAccount, "owner").scan_cursor_at
        db.close()
        return value

    def test_first_scan_reads_back_months_then_cursor_moves_to_its_start(self):
        started = utcnow()
        self.start_running("run-1", started)

        after = self.run_scan("run-1")

        self.assertIsNone(after)
        self.assertEqual(self.cursor(), started)

    def test_next_scan_reads_only_since_the_cursor(self):
        cursor = utcnow() - timedelta(days=1)
        self.start_running("run-2", utcnow(), cursor=cursor)
        # Receipts already saved, so no one-off history look-back is needed.
        db = self.Session()
        db.add(GmailReceipt(user_id="owner", gmail_message_id="m1", intermediary="netflix.com",
                            amount=20.99, currency="AUD", received_on=utcnow().date()))
        db.commit()
        db.close()

        after = self.run_scan("run-2")

        self.assertEqual(after, cursor)

    def test_account_without_saved_receipts_gets_one_full_look_back(self):
        self.start_running("run-6", utcnow(), cursor=utcnow() - timedelta(days=1))

        after = self.run_scan("run-6")

        self.assertIsNone(after)

    def test_cut_short_scan_keeps_the_cursor_so_no_email_is_skipped(self):
        cursor = utcnow() - timedelta(days=1)
        self.start_running("run-3", utcnow(), cursor=cursor)

        self.run_scan("run-3", partial=True)

        self.assertEqual(self.cursor(), cursor)

    def test_failed_scan_keeps_the_cursor(self):
        cursor = utcnow() - timedelta(days=1)
        self.start_running("run-4", utcnow(), cursor=cursor)

        self.run_scan("run-4", scan_error=RuntimeError("boom"))

        self.assertEqual(self.cursor(), cursor)

    def test_quiet_daily_scan_makes_no_duplicate_check_call(self):
        self.start_running("run-5", utcnow(), cursor=utcnow() - timedelta(days=1))
        with patch("app.gmail.analyzer.find_similar") as similar:
            scan_result = ScanResult([], 0, 0, 0, False)
            outcome = AnalysisOutcome([], 0, 0, 0, 0, False, False)
            with patch.object(gmail_router, "SessionLocal", self.Session), patch.object(
                gmail_router, "decrypt_token", return_value="token"
            ), patch("app.gmail.scanner.scan", return_value=scan_result), patch(
                "app.gmail.analyzer.analyze_bounded", return_value=outcome
            ):
                gmail_router._run_scan("owner", "run-5")
        similar.assert_not_called()

    def test_gmail_query_uses_after_for_daily_scans(self):
        self.assertIn("{window}", SEARCH_QUERY)

    def test_due_rules(self):
        now = utcnow()
        due = GmailAccount(auto_scan_enabled=True, scan_status="done", scan_started_at=now - timedelta(hours=21))
        recent = GmailAccount(auto_scan_enabled=True, scan_status="done", scan_started_at=now - timedelta(hours=2))
        never = GmailAccount(auto_scan_enabled=True, scan_status="idle", scan_started_at=None)
        off = GmailAccount(auto_scan_enabled=False, scan_status="done", scan_started_at=None)
        self.assertTrue(gmail_router.due_for_auto_scan(due, now))
        self.assertFalse(gmail_router.due_for_auto_scan(recent, now))
        self.assertTrue(gmail_router.due_for_auto_scan(never, now))
        self.assertFalse(gmail_router.due_for_auto_scan(off, now))


class ScheduledEndpointTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        db = self.Session()
        old = utcnow() - timedelta(days=2)
        db.add_all([
            GmailAccount(user_id="a", email_address="a@x", refresh_token_encrypted="e", scan_status="done", scan_started_at=old),
            GmailAccount(user_id="b", email_address="b@x", refresh_token_encrypted="e", scan_status="done", scan_started_at=old),
            GmailAccount(user_id="c", email_address="c@x", refresh_token_encrypted="e", scan_status="done", scan_started_at=old),
            GmailAccount(user_id="off", email_address="o@x", refresh_token_encrypted="e", scan_status="done",
                         scan_started_at=old, auto_scan_enabled=False),
        ])
        db.commit()
        db.close()

    def tearDown(self):
        self.engine.dispose()

    def call(self, secret="s3cret", allowed="a,b,c,off"):
        db = self.Session()
        try:
            with patch.object(gmail_router.settings, "cron_secret", "s3cret"), patch.object(
                gmail_router.settings, "gmail_oauth_user_ids", allowed
            ), patch.object(
                gmail_router, "gmail_is_configured", return_value=True
            ), patch.object(gmail_router._scan_executor, "submit"):
                return gmail_router.run_scheduled_scans(x_cron_secret=secret, db=db)
        finally:
            db.close()

    def test_wrong_or_missing_secret_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            self.call(secret="wrong")
        self.assertEqual(caught.exception.status_code, 401)
        with self.assertRaises(HTTPException):
            self.call(secret=None)

    def test_starts_as_many_as_slots_allow_and_reports_the_rest(self):
        try:
            result = self.call()
            # Two scan slots: two start now, one waits for the next call.
            self.assertEqual(result["started"], 2)
            self.assertEqual(result["remaining"], 1)
        finally:
            for _ in range(gmail_router.MAX_CONCURRENT_SCANS):
                gmail_router._scan_slots.release()

    def test_users_outside_the_oauth_list_are_skipped(self):
        try:
            result = self.call(allowed="a")
            self.assertEqual(result["started"], 1)
            self.assertEqual(result["remaining"], 0)
        finally:
            gmail_router._scan_slots.release()
        db = self.Session()
        self.assertEqual(db.get(GmailAccount, "b").scan_status, "done")
        db.close()

    def test_switched_off_accounts_are_never_scanned(self):
        try:
            self.call()
        finally:
            for _ in range(gmail_router.MAX_CONCURRENT_SCANS):
                gmail_router._scan_slots.release()
        db = self.Session()
        self.assertEqual(db.get(GmailAccount, "off").scan_status, "done")
        db.close()


if __name__ == "__main__":
    unittest.main()


class StuckScanTests(unittest.TestCase):
    def test_a_stuck_scan_does_not_count_as_running(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        long_ago = utcnow() - timedelta(hours=3)
        db.add(GmailAccount(user_id="stuck", email_address="s@x", refresh_token_encrypted="e",
                            scan_status="running", scan_started_at=long_ago, scan_heartbeat_at=long_ago,
                            auto_scan_enabled=False))
        db.commit()
        try:
            with patch.object(gmail_router.settings, "cron_secret", "s3cret"), patch.object(
                gmail_router, "gmail_is_configured", return_value=True
            ):
                result = gmail_router.run_scheduled_scans(x_cron_secret="s3cret", db=db)
            self.assertEqual(result["running"], 0)
        finally:
            db.close()
            engine.dispose()
