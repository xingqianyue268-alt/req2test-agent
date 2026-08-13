"""Relational catalog entry for a document whose vectors remain in ChromaDB."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class KnowledgeDocumentORM(TimestampMixin, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint(
            "vector_collection",
            "vector_document_id",
            name="uq_knowledge_documents_vector_reference",
        ),
        Index("ix_knowledge_documents_index_status", "index_status"),
        Index("ix_knowledge_documents_source_name", "source_name"),
        Index("ix_knowledge_documents_kind", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_name: Mapped[str] = mapped_column(String(500), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    vector_collection: Mapped[str] = mapped_column(String(255), nullable=False)
    vector_document_id: Mapped[str] = mapped_column(String(255), nullable=False)
    document_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    index_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __str__(self) -> str:
        return self.title
