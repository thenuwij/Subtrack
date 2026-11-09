"""Add day-to-day transactions, shared categories and the feature picker."""

import sqlalchemy as sa

from alembic import context, op
from app.models import Transaction

revision = "0028_transactions_and_features"
down_revision = "0027_payment_decision_amount"
branch_labels = depends_on = None

NEW_CATEGORIES = ("shopping", "health", "travel", "personal_care", "gifts", "income")


def _expand_category_enum() -> None:
    if context.is_offline_mode() or op.get_bind().dialect.name != "postgresql":
        return
    for value in NEW_CATEGORIES:
        # Values are compile-time constants, never user input.
        op.execute(sa.text(f"ALTER TYPE category ADD VALUE IF NOT EXISTS '{value}'"))


def upgrade():
    _expand_category_enum()
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("user_preferences")}
    if "enabled_features" not in columns:
        op.add_column("user_preferences", sa.Column("enabled_features", sa.JSON(), nullable=True))
    Transaction.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    Transaction.__table__.drop(op.get_bind(), checkfirst=True)
    op.drop_column("user_preferences", "enabled_features")
