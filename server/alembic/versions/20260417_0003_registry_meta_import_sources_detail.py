"""registry_cache_meta: детали импортированных PDF (sha256, часть) для merge и skip

Revision ID: 20260417_0003
Revises: 20260416_0002
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa


revision = "20260417_0003"
down_revision = "20260416_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "registry_cache_meta",
        sa.Column("import_sources_detail", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("registry_cache_meta", "import_sources_detail")
