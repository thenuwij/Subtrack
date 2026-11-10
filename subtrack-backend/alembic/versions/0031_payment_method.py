"""Record whether a recurring payment is charged automatically or paid manually,
and which due date a manual payment's transaction settled."""

import sqlalchemy as sa
from alembic import op

revision = "0031_payment_method"
down_revision = "0030_workspace_pages"
branch_labels = depends_on = None

CONSTRAINT = "ck_subscriptions_payment_method"
UNIQUE_DUE = "uq_transactions_payment_due"


def upgrade():
    bind = op.get_bind()
    # SQLite cannot add constraints to an existing table; PostgreSQL enforces them.
    postgres = bind.dialect.name == "postgresql"
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("subscriptions")}
    if "payment_method" not in columns:
        op.add_column(
            "subscriptions",
            sa.Column("payment_method", sa.String(10), nullable=False, server_default="automatic"),
        )
    checks = {check["name"] for check in inspector.get_check_constraints("subscriptions")}
    if postgres and CONSTRAINT not in checks:
        op.create_check_constraint(CONSTRAINT, "subscriptions", "payment_method IN ('automatic', 'manual')")

    transaction_columns = {column["name"] for column in inspector.get_columns("transactions")}
    if "paid_due_on" not in transaction_columns:
        op.add_column("transactions", sa.Column("paid_due_on", sa.Date(), nullable=True))
    uniques = {unique["name"] for unique in inspector.get_unique_constraints("transactions")}
    if postgres and UNIQUE_DUE not in uniques:
        op.create_unique_constraint(UNIQUE_DUE, "transactions", ["recurring_payment_id", "paid_due_on"])


def downgrade():
    # Batch mode rebuilds SQLite tables so a column named in a constraint can go.
    inspector = sa.inspect(op.get_bind())
    uniques = {unique["name"] for unique in inspector.get_unique_constraints("transactions")}
    with op.batch_alter_table("transactions") as batch:
        if UNIQUE_DUE in uniques:
            batch.drop_constraint(UNIQUE_DUE, type_="unique")
        batch.drop_column("paid_due_on")
    checks = {check["name"] for check in inspector.get_check_constraints("subscriptions")}
    with op.batch_alter_table("subscriptions") as batch:
        if CONSTRAINT in checks:
            batch.drop_constraint(CONSTRAINT, type_="check")
        batch.drop_column("payment_method")
