"""Persistent Evaluation Center runs, case results, and A/B comparisons."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import UserORM


class EvaluationRunORM(TimestampMixin, Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="status_allowed",
        ),
        CheckConstraint(
            "overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)",
            name="overall_score_range",
        ),
        Index("ix_evaluation_runs_user_created_at", "user_id", "created_at"),
        Index("ix_evaluation_runs_dataset_version", "dataset_version"),
        Index("ix_evaluation_runs_status_updated_at", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", server_default="queued"
    )
    configuration_label: Mapped[str] = mapped_column(
        String(64), nullable=False, default="single", server_default="single"
    )
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    temperature: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    judge_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    knowledge_base_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    knowledge_base_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregation_version: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_scores: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    revision_iterations: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[UserORM | None] = relationship(back_populates="evaluation_runs")
    case_results: Mapped[list[EvaluationCaseResultORM]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class EvaluationCaseResultORM(Base):
    __tablename__ = "evaluation_case_results"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "dataset_case_id", name="uq_evaluation_case_results_run_case"
        ),
        CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="overall_score_range",
        ),
        Index("ix_evaluation_case_results_run_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    dataset_case_id: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    overall_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    latency_ms: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    revision_iterations: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    generated_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[EvaluationRunORM] = relationship(back_populates="case_results")


class EvaluationComparisonORM(TimestampMixin, Base):
    __tablename__ = "evaluation_comparisons"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="status_allowed",
        ),
        CheckConstraint("run_a_id <> run_b_id", name="distinct_runs"),
        Index("ix_evaluation_comparisons_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", server_default="queued"
    )
    dataset_version: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    run_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
