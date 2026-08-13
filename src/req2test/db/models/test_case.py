"""Generated test case persistence model."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin

if TYPE_CHECKING:
    from .execution import ExecutionORM
    from .task import TaskORM


class TestCaseORM(TimestampMixin, Base):
    __tablename__ = "test_cases"
    __table_args__ = (
        UniqueConstraint("task_id", "case_id", "version", name="uq_test_cases_task_case_version"),
        Index("ix_test_cases_task_id", "task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(String(64), nullable=False)
    module: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    test_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_requirement: Mapped[str] = mapped_column(Text, nullable=False)
    preconditions: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    steps: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    task: Mapped["TaskORM"] = relationship(back_populates="test_cases")
    executions: Mapped[list["ExecutionORM"]] = relationship(back_populates="test_case")

    def __str__(self) -> str:
        return f"{self.case_id}: {self.title}"
