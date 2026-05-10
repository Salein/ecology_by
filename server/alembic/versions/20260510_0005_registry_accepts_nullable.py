"""registry_records.accepts_external_waste nullable (unknown state)

Revision ID: 20260510_0005
Revises: 20260420_0004
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260510_0005"
down_revision = "20260420_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "registry_records",
        "accepts_external_waste",
        existing_type=sa.Boolean(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE registry_records SET accepts_external_waste = true WHERE accepts_external_waste IS NULL"))
    op.alter_column(
        "registry_records",
        "accepts_external_waste",
        existing_type=sa.Boolean(),
        nullable=False,
    )
