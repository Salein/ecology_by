"""add registry_records indexes for import and stats

Revision ID: 20260420_0004
Revises: 20260417_0003
Create Date: 2026-04-20
"""

from alembic import op


revision = "20260420_0004"
down_revision = "20260417_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_registry_records_accepts_external_waste",
        "registry_records",
        ["accepts_external_waste"],
        unique=False,
    )
    op.create_index(
        "ix_registry_records_source_part_record_id",
        "registry_records",
        ["source_part", "record_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_registry_records_source_part_record_id", table_name="registry_records")
    op.drop_index("ix_registry_records_accepts_external_waste", table_name="registry_records")
