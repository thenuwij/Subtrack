"""One-off extra charges (like late fees) and remembered sender links.

Revision ID: 0021_payment_extras
Revises: 0020_gmail_auto_scan
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import context, op

revision: str = "0021_payment_extras"
down_revision: str | Sequence[str] | None = "0020_gmail_auto_scan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> set[str]:
    if context.is_offline_mode():
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    uuid_type = postgresql.UUID(as_uuid=True)
    if "payment_extras" not in tables:
        op.create_table(
            "payment_extras",
            sa.Column("id", uuid_type, primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column(
                "subscription_id", uuid_type,
                sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False),
            sa.Column("charged_at", sa.DateTime(), nullable=False),
            sa.Column("reason", sa.String(24), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.CheckConstraint("amount > 0", name="ck_payment_extras_amount"),
        )
        op.create_index("ix_payment_extras_user_charged", "payment_extras", ["user_id", "charged_at"])
    if "sender_links" not in tables:
        op.create_table(
            "sender_links",
            sa.Column("id", uuid_type, primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("sender_domain", sa.String(), nullable=False),
            sa.Column("merchant_key", sa.String(), nullable=False),
            sa.Column(
                "subscription_id", uuid_type,
                sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("user_id", "sender_domain", "merchant_key", name="uq_sender_links_sender"),
        )
        op.create_index("ix_sender_links_user_id", "sender_links", ["user_id"])
    if "detected_subscriptions" in tables:
        columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("detected_subscriptions")}
        if "last_charge_at" not in columns:
            op.add_column("detected_subscriptions", sa.Column("last_charge_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    tables = _tables()
    if "detected_subscriptions" in tables:
        op.drop_column("detected_subscriptions", "last_charge_at")
    if "sender_links" in tables:
        op.drop_index("ix_sender_links_user_id", table_name="sender_links")
        op.drop_table("sender_links")
    if "payment_extras" in tables:
        op.drop_index("ix_payment_extras_user_charged", table_name="payment_extras")
        op.drop_table("payment_extras")
