"""Private forwarding addresses and the outcome of each forwarded email."""

from alembic import op
from app.models import InboundAddress, InboundMessage

revision = "0037_inbound_email"
down_revision = "0036_remove_extras"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    InboundAddress.__table__.create(bind, checkfirst=True)
    InboundMessage.__table__.create(bind, checkfirst=True)


def downgrade():
    op.drop_table("inbound_messages")
    op.drop_table("inbound_addresses")
