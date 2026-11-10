"""Remove the extras: budgets, goals, workspace pages and the feature picker setting.

Subtrack is now one payday experience; spending pots and savings set-asides
replace budgets and goals. The transactions table stays: it holds logged
spends and payments marked paid.
"""

import sqlalchemy as sa
from alembic import op

revision = "0036_remove_extras"
down_revision = "0035_product_events"
branch_labels = depends_on = None

TABLES = ("workspace_pages", "goal_contributions", "goals", "budgets")


def upgrade():
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    for table in TABLES:
        if table in existing:
            op.drop_table(table)
    if "enabled_features" in {c["name"] for c in inspector.get_columns("user_preferences")}:
        with op.batch_alter_table("user_preferences") as batch:
            batch.drop_column("enabled_features")


def downgrade():
    # The removed features have no code left to use these tables, so only the
    # preference column comes back.
    inspector = sa.inspect(op.get_bind())
    if "enabled_features" not in {c["name"] for c in inspector.get_columns("user_preferences")}:
        op.add_column("user_preferences", sa.Column("enabled_features", sa.JSON(), nullable=True))
