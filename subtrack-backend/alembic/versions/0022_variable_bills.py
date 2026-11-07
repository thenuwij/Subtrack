"""Remember recent bills so variable bills can keep their own estimate.

Revision ID: 0022_variable_bills
Revises: 0021_payment_extras
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "0022_variable_bills"
down_revision: str | Sequence[str] | None = "0021_payment_extras"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "subscriptions"


def upgrade() -> None:
    existing: set[str] = set()
    if not context.is_offline_mode():
        existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}
    if "bill_history" not in existing:
        op.add_column(TABLE, sa.Column("bill_history", sa.JSON(), nullable=True))
    if "last_bill_at" not in existing:
        op.add_column(TABLE, sa.Column("last_bill_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column(TABLE, "last_bill_at")
    op.drop_column(TABLE, "bill_history")
