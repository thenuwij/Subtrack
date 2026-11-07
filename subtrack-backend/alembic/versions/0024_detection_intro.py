"""Keep an intro price read from email on a Gmail finding.

Revision ID: 0024_detection_intro
Revises: 0023_bills
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "0024_detection_intro"
down_revision: str | Sequence[str] | None = "0023_bills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "detected_subscriptions"


def upgrade() -> None:
    if not context.is_offline_mode():
        inspector = sa.inspect(op.get_bind())
        if TABLE not in inspector.get_table_names():
            return
        if "intro_amount" in {c["name"] for c in inspector.get_columns(TABLE)}:
            return
    op.add_column(TABLE, sa.Column("intro_amount", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column(TABLE, "intro_amount")
