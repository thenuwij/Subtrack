"""Manual payment confirmations, separate from receipt evidence."""
from alembic import op
from app.models import PaymentDecision
revision = "0025_payment_decisions"
down_revision = "0024_detection_intro"
branch_labels = depends_on = None

def upgrade():
    PaymentDecision.__table__.create(op.get_bind(), checkfirst=True)

def downgrade():
    PaymentDecision.__table__.drop(op.get_bind(), checkfirst=True)
