"""Workspace pages (removed).

The custom workspace was removed in 0036_remove_extras. This revision is kept
as a no-op so the migration chain stays linear; 0036 drops the table on
databases that already have it.
"""

revision = "0030_workspace_pages"
down_revision = "0029_budgets_and_goals"
branch_labels = depends_on = None


def upgrade():
    pass


def downgrade():
    pass
