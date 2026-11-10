"""Category budgets, savings goals and goal contributions (removed).

These features were removed in 0036_remove_extras. This revision is kept as a
no-op so the migration chain stays linear; 0036 drops the tables on databases
that already have them.
"""

revision = "0029_budgets_and_goals"
down_revision = "0028_transactions_and_features"
branch_labels = depends_on = None


def upgrade():
    pass


def downgrade():
    pass
