"""Add accounts, transactions, receipts, links, rules and goals.

Revision ID: 0015_pay_cycle_ledger
Revises: 0014_drop_legacy_tables
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import context, op

revision: str = "0015_pay_cycle_ledger"
down_revision: str | Sequence[str] | None = "0014_drop_legacy_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
MONEY = sa.Numeric(12, 2)


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


def _updated_at() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.DateTime(),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


def _create_bank_accounts() -> None:
    op.create_table(
        "bank_accounts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("institution", sa.String(length=40), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("account_last4", sa.String(length=4), nullable=True),
        _created_at(),
        sa.UniqueConstraint("user_id", "name", name="uq_bank_accounts_user_name"),
        sa.CheckConstraint(
            "purpose IN ('everyday', 'savings', 'other')",
            name="ck_bank_accounts_purpose",
        ),
    )
    op.create_index("ix_bank_accounts_user_id", "bank_accounts", ["user_id"])


def _create_statement_imports() -> None:
    op.create_table(
        "statement_imports",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column(
            "bank_account_id",
            UUID,
            sa.ForeignKey("bank_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("first_posted_on", sa.Date(), nullable=True),
        sa.Column("last_posted_on", sa.Date(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        _created_at(),
    )
    op.create_index("ix_statement_imports_user_id", "statement_imports", ["user_id"])
    op.create_index(
        "ix_statement_imports_bank_account_id", "statement_imports", ["bank_account_id"]
    )


def _create_bank_transactions() -> None:
    op.create_table(
        "bank_transactions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column(
            "bank_account_id",
            UUID,
            sa.ForeignKey("bank_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "statement_import_id",
            UUID,
            sa.ForeignKey("statement_imports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("posted_on", sa.Date(), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("balance", MONEY, nullable=True),
        sa.Column("dedupe_hash", sa.String(length=64), nullable=False),
        _created_at(),
        sa.UniqueConstraint(
            "bank_account_id", "dedupe_hash", name="uq_bank_transactions_account_dedupe"
        ),
    )
    op.create_index(
        "ix_bank_transactions_user_posted", "bank_transactions", ["user_id", "posted_on"]
    )
    op.create_index(
        "ix_bank_transactions_bank_account_id", "bank_transactions", ["bank_account_id"]
    )
    op.create_index(
        "ix_bank_transactions_statement_import_id", "bank_transactions", ["statement_import_id"]
    )


def _create_gmail_receipts() -> None:
    op.create_table(
        "gmail_receipts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=64), nullable=False),
        sa.Column("intermediary", sa.String(length=40), nullable=False),
        sa.Column("merchant", sa.String(length=200), nullable=True),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("purchase_total", MONEY, nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("instalment_number", sa.Integer(), nullable=True),
        sa.Column("instalment_count", sa.Integer(), nullable=True),
        sa.Column("received_on", sa.Date(), nullable=False),
        _created_at(),
        sa.UniqueConstraint(
            "user_id", "gmail_message_id", name="uq_gmail_receipts_user_message"
        ),
    )
    op.create_index(
        "ix_gmail_receipts_user_received", "gmail_receipts", ["user_id", "received_on"]
    )


def _create_transaction_links() -> None:
    op.create_table(
        "transaction_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("link_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "transaction_id",
            UUID,
            sa.ForeignKey("bank_transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "counterpart_transaction_id",
            UUID,
            sa.ForeignKey("bank_transactions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "gmail_receipt_id",
            UUID,
            sa.ForeignKey("gmail_receipts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        _created_at(),
        sa.CheckConstraint(
            "link_type IN ('transfer', 'intermediary')",
            name="ck_transaction_links_type",
        ),
        sa.CheckConstraint(
            "status IN ('suggested', 'confirmed')",
            name="ck_transaction_links_status",
        ),
        sa.CheckConstraint(
            "(link_type = 'transfer' AND counterpart_transaction_id IS NOT NULL) "
            "OR (link_type = 'intermediary' AND gmail_receipt_id IS NOT NULL)",
            name="ck_transaction_links_target",
        ),
    )
    for column in (
        "user_id",
        "transaction_id",
        "counterpart_transaction_id",
        "gmail_receipt_id",
    ):
        op.create_index(f"ix_transaction_links_{column}", "transaction_links", [column])


def _create_money_rules() -> None:
    op.create_table(
        "money_rules",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("match_text", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint("user_id", "match_text", name="uq_money_rules_user_match"),
        sa.CheckConstraint(
            "kind IN ('pay', 'other_income', 'bill', 'spending', 'transfer', 'ignore')",
            name="ck_money_rules_kind",
        ),
    )
    op.create_index("ix_money_rules_user_id", "money_rules", ["user_id"])


def _create_money_goals() -> None:
    op.create_table(
        "money_goals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column(
            "bank_account_id",
            UUID,
            sa.ForeignKey("bank_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("target_amount", MONEY, nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_money_goals_user_id", "money_goals", ["user_id"])
    op.create_index("ix_money_goals_bank_account_id", "money_goals", ["bank_account_id"])


TABLES = {
    "bank_accounts": _create_bank_accounts,
    "statement_imports": _create_statement_imports,
    "bank_transactions": _create_bank_transactions,
    "gmail_receipts": _create_gmail_receipts,
    "transaction_links": _create_transaction_links,
    "money_rules": _create_money_rules,
    "money_goals": _create_money_goals,
}


def upgrade() -> None:
    existing = (
        set() if context.is_offline_mode() else set(sa.inspect(op.get_bind()).get_table_names())
    )
    for name, create in TABLES.items():
        if name not in existing:
            create()


def downgrade() -> None:
    for name in reversed(TABLES):
        op.drop_table(name)
