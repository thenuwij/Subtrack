"""Let a manual paid answer record the amount actually paid."""

import sqlalchemy as sa
from alembic import op

revision = "0027_payment_decision_amount"
down_revision = "0026_email_reminders"
branch_labels = depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("payment_decisions")}
    if "amount" not in columns:
        op.add_column("payment_decisions", sa.Column("amount", sa.Numeric(12, 2), nullable=True))


def downgrade():
    op.drop_column("payment_decisions", "amount")
