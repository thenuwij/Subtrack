"""Daily automatic Gmail scans: an on/off switch and a success-only cursor.

Revision ID: 0020_gmail_auto_scan
Revises: 0019_intro_amount
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "0020_gmail_auto_scan"
down_revision: str | Sequence[str] | None = "0019_intro_amount"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "gmail_accounts"


def upgrade() -> None:
    existing: set[str] = set()
    if not context.is_offline_mode():
        inspector = sa.inspect(op.get_bind())
        # Older databases create this table later from the models, with the
        # columns already present.
        if TABLE not in inspector.get_table_names():
            return
        existing = {c["name"] for c in inspector.get_columns(TABLE)}
    if "auto_scan_enabled" not in existing:
        op.add_column(
            TABLE,
            sa.Column("auto_scan_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if "scan_cursor_at" not in existing:
        op.add_column(TABLE, sa.Column("scan_cursor_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    if not context.is_offline_mode() and TABLE not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_column(TABLE, "scan_cursor_at")
    op.drop_column(TABLE, "auto_scan_enabled")
