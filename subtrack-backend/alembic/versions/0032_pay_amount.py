"""Let safe to spend work without a balance by storing the user's usual pay."""

import sqlalchemy as sa
from alembic import op

revision = "0032_pay_amount"
down_revision = "0031_payment_method"
branch_labels = depends_on = None

TABLE = "safe_to_spend_profiles"


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}
    with op.batch_alter_table(TABLE) as batch:
        if "pay_amount" not in columns:
            batch.add_column(sa.Column("pay_amount", sa.Numeric(12, 2), nullable=True))
        batch.alter_column("balance", existing_type=sa.Numeric(12, 2), nullable=True)
        batch.alter_column("balance_as_of", existing_type=sa.DateTime(), nullable=True)


def downgrade():
    # Profiles saved without a balance cannot satisfy NOT NULL, so they go.
    op.execute(sa.text(f"DELETE FROM {TABLE} WHERE balance IS NULL OR balance_as_of IS NULL"))
    with op.batch_alter_table(TABLE) as batch:
        batch.alter_column("balance_as_of", existing_type=sa.DateTime(), nullable=False)
        batch.alter_column("balance", existing_type=sa.Numeric(12, 2), nullable=False)
        batch.drop_column("pay_amount")
