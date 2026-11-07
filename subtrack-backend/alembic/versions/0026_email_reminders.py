"""Opt-in email preferences and durable delivery identities."""
from alembic import op
from app.models import EmailPreference, ReminderDelivery
revision = "0026_email_reminders"
down_revision = "0025_payment_decisions"
branch_labels = depends_on = None

def upgrade():
    for model in (EmailPreference, ReminderDelivery):
        model.__table__.create(op.get_bind(), checkfirst=True)

def downgrade():
    for model in (ReminderDelivery, EmailPreference):
        model.__table__.drop(op.get_bind(), checkfirst=True)
