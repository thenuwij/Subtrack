"""Keep Gmail's confirm link, which newer forwarding confirmations send in place of a code."""

import sqlalchemy as sa
from alembic import op

revision = "0038_inbound_confirmation_url"
down_revision = "0037_inbound_email"
branch_labels = depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("inbound_addresses")}
    if "confirmation_url" not in columns:
        op.add_column("inbound_addresses", sa.Column("confirmation_url", sa.String(2048), nullable=True))


def downgrade():
    with op.batch_alter_table("inbound_addresses") as batch:
        batch.drop_column("confirmation_url")
