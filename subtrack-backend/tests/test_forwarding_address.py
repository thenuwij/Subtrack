import os
import unittest
from datetime import timedelta
from unittest.mock import patch
from xml.etree import ElementTree

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.database import Base, get_db  # noqa: E402
from app.middleware.auth import verify_token  # noqa: E402
from app.models import InboundAddress, InboundMessage  # noqa: E402
from app.routers import inbound  # noqa: E402


class ForwardingAddressTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.user = "alice"
        app = FastAPI()
        app.include_router(inbound.router)

        def override_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[verify_token] = lambda: self.user
        self.client = TestClient(app)
        patcher = patch.object(inbound.settings, "inbound_email_domain", "pocketday.app")
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.engine.dispose()

    def row(self, user="alice"):
        db = self.Session()
        try:
            return db.query(InboundAddress).filter(InboundAddress.user_id == user).first()
        finally:
            db.close()

    def edit(self, **fields):
        db = self.Session()
        db.query(InboundAddress).filter(InboundAddress.user_id == "alice").update(fields)
        db.commit()
        db.close()

    def test_address_is_created_once_and_reused(self):
        first = self.client.get("/inbound/address").json()
        second = self.client.get("/inbound/address").json()
        self.assertEqual(first["address"], second["address"])
        self.assertTrue(first["address"].endswith("@pocketday.app"))
        self.assertEqual(len(first["address"].split("@")[0]), 20)
        self.assertEqual(first["status"], "pending")
        self.assertEqual(first["received_count"], 0)

    def test_other_users_address_is_never_visible(self):
        mine = self.client.get("/inbound/address").json()["address"]
        self.user = "bob"
        theirs = self.client.get("/inbound/address").json()["address"]
        self.assertNotEqual(mine, theirs)
        self.user = "alice"
        self.assertEqual(self.client.get("/inbound/address").json()["address"], mine)

    def test_rotate_changes_token_and_clears_gmail(self):
        before = self.client.get("/inbound/address").json()["address"]
        self.edit(
            gmail_address="a@gmail.com", status="active", confirmation_code="123456",
            confirmation_url="https://mail.google.com/mail/vf-x",
        )
        after = self.client.post("/inbound/address/rotate").json()
        self.assertNotEqual(before, after["address"])
        self.assertEqual(after["status"], "pending")
        self.assertIsNone(after["gmail_address"])
        self.assertIsNone(after["confirmation_code"])
        self.assertIsNone(self.row().confirmation_url)
        self.assertIsNotNone(self.row().rotated_at)

    def test_pause_and_resume(self):
        self.client.get("/inbound/address")
        self.assertEqual(self.client.patch("/inbound/address", json={"paused": True}).json()["status"], "paused")
        self.assertEqual(self.client.patch("/inbound/address", json={"paused": False}).json()["status"], "pending")
        self.edit(gmail_address="a@gmail.com")
        self.client.patch("/inbound/address", json={"paused": True})
        self.assertEqual(self.client.patch("/inbound/address", json={"paused": False}).json()["status"], "active")

    def test_delete_removes_address_and_messages(self):
        self.client.get("/inbound/address")
        db = self.Session()
        db.add(InboundMessage(user_id="alice", message_hash="h1", outcome="accepted"))
        db.commit()
        db.close()
        self.assertEqual(self.client.delete("/inbound/address").status_code, 204)
        self.assertIsNone(self.row())
        db = self.Session()
        self.assertEqual(db.query(InboundMessage).count(), 0)
        db.close()

    def test_code_hidden_after_24_hours_or_when_active(self):
        self.client.get("/inbound/address")
        now = inbound._utcnow()
        link = "https://mail.google.com/mail/vf-x"
        self.edit(confirmation_code="123456", confirmation_url=link, confirmation_received_at=now)
        shown = self.client.get("/inbound/address").json()
        self.assertEqual((shown["confirmation_code"], shown["confirmation_url"]), ("123456", link))
        self.edit(confirmation_received_at=now - timedelta(hours=25))
        expired = self.client.get("/inbound/address").json()
        self.assertEqual((expired["confirmation_code"], expired["confirmation_url"]), (None, None))
        self.edit(confirmation_received_at=now, status="active")
        active = self.client.get("/inbound/address").json()
        self.assertEqual((active["confirmation_code"], active["confirmation_url"]), (None, None))

    def test_received_count_counts_only_accepted(self):
        self.client.get("/inbound/address")
        db = self.Session()
        db.add_all([
            InboundMessage(user_id="alice", message_hash="a", outcome="accepted"),
            InboundMessage(user_id="alice", message_hash="b", outcome="filtered"),
            InboundMessage(user_id="bob", message_hash="c", outcome="accepted"),
        ])
        db.commit()
        db.close()
        body = self.client.get("/inbound/address").json()
        self.assertEqual(body["received_count"], 1)
        self.assertIsNotNone(body["last_received_at"])

    def test_filter_xml_forwards_to_address(self):
        address = self.client.get("/inbound/address").json()["address"]
        response = self.client.get("/inbound/filter.xml")
        self.assertIn('filename="pocketday-filter.xml"', response.headers["content-disposition"])
        root = ElementTree.fromstring(response.text)
        values = {p.get("name"): p.get("value") for p in root.iter("{http://schemas.google.com/apps/2006}property")}
        self.assertEqual(values["forwardTo"], address)
        self.assertEqual(values["hasTheWord"], inbound.BILL_SEARCH)


if __name__ == "__main__":
    unittest.main()
