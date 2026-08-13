"""Create the initial Req2Test business tables.

Revision ID: 20260813_0001
Revises:
Create Date: 2026-08-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260813_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="member", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("stage", sa.String(length=64), server_default="queued", nullable=False),
        sa.Column("progress", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("state_version", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "generation_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "execution_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("result_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "progress >= 0 AND progress <= 100", name=op.f("ck_tasks_progress_range")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_tasks_user_id_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
    )
    op.create_index("ix_tasks_status_updated_at", "tasks", ["status", "updated_at"])
    op.create_index("ix_tasks_user_id_created_at", "tasks", ["user_id", "created_at"])
    op.create_index(
        "uq_tasks_celery_task_id_not_null",
        "tasks",
        ["celery_task_id"],
        unique=True,
        postgresql_where=sa.text("celery_task_id IS NOT NULL"),
    )

    op.create_table(
        "test_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("module", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("test_type", sa.String(length=32), nullable=False),
        sa.Column("source_requirement", sa.Text(), nullable=False),
        sa.Column(
            "preconditions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "steps",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name="fk_test_cases_task_id_tasks", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_test_cases"),
        sa.UniqueConstraint(
            "task_id", "case_id", "version", name="uq_test_cases_task_case_version"
        ),
    )
    op.create_index("ix_test_cases_task_id", "test_cases", ["task_id"])

    op.create_table(
        "executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=True),
        sa.Column("path", sa.String(length=2048), nullable=True),
        sa.Column("expected_status", sa.Integer(), nullable=True),
        sa.Column("actual_status", sa.Integer(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("duration_ms", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("response_excerpt", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("failure_category", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], name="fk_executions_task_id_tasks", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["test_case_id"],
            ["test_cases.id"],
            name="fk_executions_test_case_id_test_cases",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_executions"),
        sa.UniqueConstraint("idempotency_key", name="uq_executions_idempotency_key"),
    )
    op.create_index("ix_executions_failure_category", "executions", ["failure_category"])
    op.create_index("ix_executions_task_id_created_at", "executions", ["task_id", "created_at"])
    op.create_index("ix_executions_task_id_passed", "executions", ["task_id", "passed"])

    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("source_name", sa.String(length=500), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("vector_collection", sa.String(length=255), nullable=False),
        sa.Column("vector_document_id", sa.String(length=255), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("index_status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_documents"),
        sa.UniqueConstraint(
            "vector_collection",
            "vector_document_id",
            name="uq_knowledge_documents_vector_reference",
        ),
    )
    op.create_index("ix_knowledge_documents_index_status", "knowledge_documents", ["index_status"])
    op.create_index("ix_knowledge_documents_kind", "knowledge_documents", ["kind"])
    op.create_index("ix_knowledge_documents_source_name", "knowledge_documents", ["source_name"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_source_name", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_kind", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_index_status", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")

    op.drop_index("ix_executions_task_id_passed", table_name="executions")
    op.drop_index("ix_executions_task_id_created_at", table_name="executions")
    op.drop_index("ix_executions_failure_category", table_name="executions")
    op.drop_table("executions")

    op.drop_index("ix_test_cases_task_id", table_name="test_cases")
    op.drop_table("test_cases")

    op.drop_index("uq_tasks_celery_task_id_not_null", table_name="tasks")
    op.drop_index("ix_tasks_user_id_created_at", table_name="tasks")
    op.drop_index("ix_tasks_status_updated_at", table_name="tasks")
    op.drop_table("tasks")
    op.drop_table("users")
