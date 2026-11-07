"""Add an optional intro price to free trials.

Revision ID: 0019_intro_amount
Revises: 0018_payday_bills_after_pay
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "0019_intro_amount"
down_revision: str | Sequence[str] | None = "0018_payday_bills_after_pay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "subscriptions"
COLUMN = "intro_amount"


def upgrade() -> None:
    # Fresh databases build this table from the current models.
    if not context.is_offline_mode():
        columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}
        if COLUMN in columns:
            return
    op.add_column(TABLE, sa.Column(COLUMN, sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column(TABLE, COLUMN)
