"""Long-lived test task persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin

if TYPE_CHECKING:
    from .execution import ExecutionORM
    from .test_case import TestCaseORM
    from .user import UserORM


class TaskORM(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("progress >= 0 AND progress <= 100", name="progress_range"),
        Index(
            "uq_tasks_celery_task_id_not_null",
            "celery_task_id",
            unique=True,
            postgresql_where=text("celery_task_id IS NOT NULL"),
        ),
        Index("ix_tasks_user_id_created_at", "user_id", "created_at"),
        Index("ix_tasks_status_updated_at", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", server_default="queued"
    )
    stage: Mapped[str] = mapped_column(
        String(64), nullable=False, default="queued", server_default="queued"
    )
    progress: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    state_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    generation_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    execution_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["UserORM | None"] = relationship(back_populates="tasks")
    test_cases: Mapped[list["TestCaseORM"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", passive_deletes=True
    )
    executions: Mapped[list["ExecutionORM"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", passive_deletes=True
    )

    def __str__(self) -> str:
        return self.title
