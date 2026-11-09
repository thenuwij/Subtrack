"""Add workspace pages, saved layouts built from the fixed blocks."""

from alembic import op
from app.models import WorkspacePage

revision = "0030_workspace_pages"
down_revision = "0029_budgets_and_goals"
branch_labels = depends_on = None


def upgrade():
    WorkspacePage.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    op.drop_table("workspace_pages")
