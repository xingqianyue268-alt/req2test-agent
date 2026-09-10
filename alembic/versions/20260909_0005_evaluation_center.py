"""Add persistent Evaluation Center runs and comparisons.

Revision ID: 20260909_0005
Revises: 20260814_0004
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260909_0005"
down_revision: str | None = "20260814_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column(
            "configuration_label", sa.String(length=64), server_default="single", nullable=False
        ),
        sa.Column("dataset_name", sa.String(length=255), nullable=False),
        sa.Column("dataset_version", sa.String(length=128), nullable=False),
        sa.Column("dataset_digest", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("temperature", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=True),
        sa.Column("prompt_version", sa.String(length=128), nullable=False),
        sa.Column("prompt_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "generation_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "judge_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("knowledge_base_identifier", sa.String(length=255), nullable=False),
        sa.Column("knowledge_base_digest", sa.String(length=64), nullable=False),
        sa.Column("aggregation_version", sa.String(length=128), nullable=False),
        sa.Column(
            "metric_scores",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("overall_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("revision_iterations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)",
            name=op.f("ck_evaluation_runs_overall_score_range"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name=op.f("ck_evaluation_runs_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_evaluation_runs_user_id_users", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_runs"),
    )
    op.create_index(
        "ix_evaluation_runs_dataset_version", "evaluation_runs", ["dataset_version"]
    )
    op.create_index(
        "ix_evaluation_runs_status_updated_at", "evaluation_runs", ["status", "updated_at"]
    )
    op.create_index(
        "ix_evaluation_runs_user_created_at", "evaluation_runs", ["user_id", "created_at"]
    )

    op.create_table(
        "evaluation_case_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_case_id", sa.String(length=128), nullable=False),
        sa.Column("metric_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("overall_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("latency_ms", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("revision_iterations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("judge_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name=op.f("ck_evaluation_case_results_overall_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evaluation_runs.id"],
            name="fk_evaluation_case_results_run_id_evaluation_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_case_results"),
        sa.UniqueConstraint(
            "run_id",
            "dataset_case_id",
            name="uq_evaluation_case_results_run_case",
        ),
    )
    op.create_index(
        "ix_evaluation_case_results_run_id", "evaluation_case_results", ["run_id"]
    )

    op.create_table(
        "evaluation_comparisons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("dataset_version", sa.String(length=128), nullable=False),
        sa.Column("dataset_digest", sa.String(length=64), nullable=False),
        sa.Column("run_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "run_a_id <> run_b_id", name=op.f("ck_evaluation_comparisons_distinct_runs")
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name=op.f("ck_evaluation_comparisons_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["run_a_id"],
            ["evaluation_runs.id"],
            name="fk_evaluation_comparisons_run_a_id_evaluation_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_b_id"],
            ["evaluation_runs.id"],
            name="fk_evaluation_comparisons_run_b_id_evaluation_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_evaluation_comparisons_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_comparisons"),
    )
    op.create_index(
        "ix_evaluation_comparisons_user_created_at",
        "evaluation_comparisons",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evaluation_comparisons_user_created_at", table_name="evaluation_comparisons"
    )
    op.drop_table("evaluation_comparisons")
    op.drop_index("ix_evaluation_case_results_run_id", table_name="evaluation_case_results")
    op.drop_table("evaluation_case_results")
    op.drop_index("ix_evaluation_runs_user_created_at", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_status_updated_at", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_dataset_version", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
