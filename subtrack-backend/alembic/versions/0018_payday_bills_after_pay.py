"""Let people say their pay lands before bills due on payday.

Revision ID: 0018_payday_bills_after_pay
Revises: 0017_ai_call_traces
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

TABLE = "safe_to_spend_profiles"
COLUMN = "payday_bills_after_pay"

revision: str = "0018_payday_bills_after_pay"
down_revision: str | Sequence[str] | None = "0017_ai_call_traces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fresh databases build this table from the current models, so the column
    # may already be there.
    if not context.is_offline_mode():
        columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}
        if COLUMN in columns:
            return
    op.add_column(
        TABLE,
        sa.Column(COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column(TABLE, COLUMN)
