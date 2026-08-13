"""Persist reconstructable knowledge document source text.

Revision ID: 20260813_0003
Revises: 20260813_0002
Create Date: 2026-08-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_0003"
down_revision: str | None = "20260813_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("content_text", sa.Text(), server_default="", nullable=False),
    )
    op.alter_column("knowledge_documents", "content_text", server_default=None)


def downgrade() -> None:
    op.drop_column("knowledge_documents", "content_text")
