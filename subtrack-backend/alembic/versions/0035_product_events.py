"""Anonymous usage events for activation and retention counts."""

from alembic import op
from app.models import ProductEvent

revision = "0035_product_events"
down_revision = "0034_set_asides"
branch_labels = depends_on = None


def upgrade():
    ProductEvent.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    op.drop_table("product_events")
