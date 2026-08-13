"""Store indexed chunk counts on knowledge catalog rows.

Revision ID: 20260814_0004
Revises: 20260813_0003
"""

from alembic import op
import sqlalchemy as sa

revision = "20260814_0004"
down_revision = "20260813_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("knowledge_documents", "chunk_count")
