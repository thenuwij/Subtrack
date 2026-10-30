import os
import unittest

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.config import assert_safe_migration_target

REMOTE_URL = "postgresql://user:pass@ep-prod.neon.tech/db?sslmode=require"


class MigrationGuardTests(unittest.TestCase):
    def test_remote_database_is_refused_outside_production(self):
        with self.assertRaises(RuntimeError):
            assert_safe_migration_target(REMOTE_URL, "development", "")

    def test_other_remote_host_is_refused_when_one_is_allowed(self):
        with self.assertRaises(RuntimeError):
            assert_safe_migration_target(REMOTE_URL, "development", "ep-dev.neon.tech")

    def test_allowed_targets_pass(self):
        assert_safe_migration_target(REMOTE_URL, "production", "")
        assert_safe_migration_target(REMOTE_URL, "development", "ep-prod.neon.tech")
        assert_safe_migration_target("sqlite://", "development", "")
        assert_safe_migration_target("postgresql://localhost/db", "test", "")
