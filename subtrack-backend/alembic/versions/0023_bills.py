"""Bills read from email, so receipts can mark them paid.

Revision ID: 0023_bills
Revises: 0022_variable_bills
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import context, op

revision: str = "0023_bills"
down_revision: str | Sequence[str] | None = "0022_variable_bills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if not context.is_offline_mode() and "bills" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "bills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("gmail_message_id", sa.String(64), nullable=False),
        sa.Column("intermediary", sa.String(80), nullable=False),
        sa.Column("merchant", sa.String(200), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("late_fee", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("user_id", "gmail_message_id", name="uq_bills_user_message"),
    )
    op.create_index("ix_bills_user_issued", "bills", ["user_id", "issued_on"])


def downgrade() -> None:
    op.drop_index("ix_bills_user_issued", table_name="bills")
    op.drop_table("bills")
