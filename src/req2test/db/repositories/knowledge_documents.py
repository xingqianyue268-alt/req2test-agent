"""Repository operations for the PostgreSQL knowledge document catalog."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import KnowledgeDocumentORM


def list_documents(
    session: Session, *, page: int = 1, page_size: int = 50
) -> tuple[list[KnowledgeDocumentORM], int]:
    total = session.scalar(select(func.count()).select_from(KnowledgeDocumentORM)) or 0
    documents = list(
        session.scalars(
            select(KnowledgeDocumentORM)
            .order_by(KnowledgeDocumentORM.created_at.desc(), KnowledgeDocumentORM.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return documents, int(total)


def get_document(session: Session, document_id: uuid.UUID) -> KnowledgeDocumentORM | None:
    return session.get(KnowledgeDocumentORM, document_id)


def get_by_vector_reference(
    session: Session, *, collection: str, vector_document_id: str
) -> KnowledgeDocumentORM | None:
    return session.scalar(
        select(KnowledgeDocumentORM).where(
            KnowledgeDocumentORM.vector_collection == collection,
            KnowledgeDocumentORM.vector_document_id == vector_document_id,
        )
    )


def all_documents(session: Session) -> list[KnowledgeDocumentORM]:
    return list(session.scalars(select(KnowledgeDocumentORM).order_by(KnowledgeDocumentORM.id)))


def create_document(
    session: Session,
    *,
    title: str,
    source_name: str,
    kind: str,
    vector_collection: str,
    vector_document_id: str,
    content_text: str,
    metadata: dict,
) -> KnowledgeDocumentORM:
    document = KnowledgeDocumentORM(
        id=uuid.uuid4(),
        title=title,
        source_name=source_name,
        kind=kind,
        vector_collection=vector_collection,
        vector_document_id=vector_document_id,
        content_text=content_text,
        document_metadata=metadata,
        index_status="pending",
    )
    session.add(document)
    session.flush()
    return document


def set_index_state(
    session: Session,
    document: KnowledgeDocumentORM,
    status: str,
    *,
    error: str | None = None,
) -> KnowledgeDocumentORM:
    document.index_status = status
    document.error = error
    session.flush()
    return document


def delete_document(session: Session, document: KnowledgeDocumentORM) -> None:
    session.delete(document)
    session.flush()
