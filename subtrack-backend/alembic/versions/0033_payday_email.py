"""Let users opt in to a payday email, separate from payment reminders."""

import sqlalchemy as sa
from alembic import op

revision = "0033_payday_email"
down_revision = "0032_pay_amount"
branch_labels = depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("email_preferences")}
    if "payday_enabled" not in columns:
        op.add_column(
            "email_preferences",
            sa.Column("payday_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade():
    with op.batch_alter_table("email_preferences") as batch:
        batch.drop_column("payday_enabled")
