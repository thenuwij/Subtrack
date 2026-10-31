"""Add the safe-to-spend profile table.

Revision ID: 0016_safe_to_spend_profiles
Revises: 0015_pay_cycle_ledger
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "0016_safe_to_spend_profiles"
down_revision: str | Sequence[str] | None = "0015_pay_cycle_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "safe_to_spend_profiles"


def upgrade() -> None:
    if not context.is_offline_mode() and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("user_id", sa.String(), primary_key=True),
        sa.Column("balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("balance_as_of", sa.DateTime(), nullable=False),
        sa.Column("pay_anchor_on", sa.Date(), nullable=False),
        sa.Column("pay_interval_unit", sa.String(length=12), nullable=False),
        sa.Column("pay_interval_count", sa.Integer(), nullable=False),
        sa.Column("buffer", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "pay_interval_unit IN ('week', 'month')",
            name="ck_safe_to_spend_pay_unit",
        ),
        sa.CheckConstraint(
            "pay_interval_count >= 1 AND pay_interval_count <= 12",
            name="ck_safe_to_spend_pay_count",
        ),
        sa.CheckConstraint("buffer >= 0", name="ck_safe_to_spend_buffer"),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
