"""Money set aside each pay (savings and spending pots), and which pot a spend used."""

import sqlalchemy as sa
from alembic import op
from app.models import SetAside

revision = "0034_set_asides"
down_revision = "0033_payday_email"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    SetAside.__table__.create(bind, checkfirst=True)
    columns = {column["name"] for column in sa.inspect(bind).get_columns("transactions")}
    if "set_aside_id" not in columns:
        op.add_column("transactions", sa.Column("set_aside_id", sa.Uuid(), nullable=True))


def downgrade():
    with op.batch_alter_table("transactions") as batch:
        batch.drop_column("set_aside_id")
    op.drop_table("set_asides")
