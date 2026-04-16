"""create users table

Revision ID: 20260416_0001
Revises: None
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa


revision = "20260416_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("last_seen_at", sa.String(length=64), nullable=True),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("subscription_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_blocked", "users", ["blocked"], unique=False)
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index("ix_users_role", "users", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_blocked", table_name="users")
    op.drop_table("users")
