"""Constrain authentication roles to user and admin.

Revision ID: 20260813_0002
Revises: 20260813_0001
Create Date: 2026-08-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_0002"
down_revision: str | None = "20260813_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE users SET role = 'user' WHERE role = 'member'")
    op.alter_column("users", "role", server_default="user", existing_type=sa.String(32))
    op.create_check_constraint(
        op.f("ck_users_role_allowed"), "users", "role IN ('user', 'admin')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_role_allowed"), "users", type_="check")
    op.execute("UPDATE users SET role = 'member' WHERE role = 'user'")
    op.alter_column("users", "role", server_default="member", existing_type=sa.String(32))
