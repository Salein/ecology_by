"""create registry and geocode tables

Revision ID: 20260416_0002
Revises: 20260416_0001
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa


revision = "20260416_0002"
down_revision = "20260416_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registry_cache_meta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.Column("source_signature", sa.String(length=128), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "registry_records",
        sa.Column("pk", sa.Integer(), nullable=False),
        sa.Column("source_part", sa.Integer(), nullable=True),
        sa.Column("record_id", sa.Integer(), nullable=True),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("object_name", sa.Text(), nullable=False),
        sa.Column("waste_code", sa.String(length=32), nullable=True),
        sa.Column("waste_type_name", sa.Text(), nullable=True),
        sa.Column("accepts_external_waste", sa.Boolean(), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("phones", sa.Text(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("pk"),
    )
    op.create_index("ix_registry_records_record_id", "registry_records", ["record_id"], unique=False)
    op.create_index("ix_registry_records_source_part", "registry_records", ["source_part"], unique=False)
    op.create_index("ix_registry_records_waste_code", "registry_records", ["waste_code"], unique=False)
    op.create_index(
        "ix_registry_records_record_id_waste_code",
        "registry_records",
        ["record_id", "waste_code"],
        unique=False,
    )

    op.create_table(
        "geocode_cache",
        sa.Column("key", sa.String(length=280), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("geocode_cache")
    op.drop_index("ix_registry_records_record_id_waste_code", table_name="registry_records")
    op.drop_index("ix_registry_records_waste_code", table_name="registry_records")
    op.drop_index("ix_registry_records_source_part", table_name="registry_records")
    op.drop_index("ix_registry_records_record_id", table_name="registry_records")
    op.drop_table("registry_records")
    op.drop_table("registry_cache_meta")
