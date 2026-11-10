"""Add category budgets, savings goals and goal contributions."""

from alembic import op
from app.models import Budget, Goal, GoalContribution

revision = "0029_budgets_and_goals"
down_revision = "0028_transactions_and_features"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    Budget.__table__.create(bind, checkfirst=True)
    Goal.__table__.create(bind, checkfirst=True)
    GoalContribution.__table__.create(bind, checkfirst=True)


def downgrade():
    # op.drop_table leaves the shared category enum in place for other tables.
    for table in ("goal_contributions", "goals", "budgets"):
        op.drop_table(table)
