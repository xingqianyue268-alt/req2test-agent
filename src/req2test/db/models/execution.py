"""HTTP and Pytest execution result persistence model."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

if TYPE_CHECKING:
    from .task import TaskORM
    from .test_case import TestCaseORM


class ExecutionORM(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_executions_idempotency_key"),
        Index("ix_executions_task_id_created_at", "task_id", "created_at"),
        Index("ix_executions_task_id_passed", "task_id", "passed"),
        Index("ix_executions_failure_category", "failure_category"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    test_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    expected_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    duration_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    response_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    task: Mapped["TaskORM"] = relationship(back_populates="executions")
    test_case: Mapped["TestCaseORM | None"] = relationship(back_populates="executions")

    def __str__(self) -> str:
        return f"{self.kind}:{self.idempotency_key}"
