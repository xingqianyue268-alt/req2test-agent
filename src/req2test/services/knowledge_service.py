"""Product service coordinating PostgreSQL knowledge metadata and Chroma vectors."""

from __future__ import annotations

import base64
import binascii
import hashlib
import math
import os
import re
import uuid
from pathlib import Path, PurePath
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.models import KnowledgeDocumentORM
from ..db.repositories import knowledge_documents as repository
from ..document_loader import SUPPORTED_SUFFIXES, load_document_bytes
from ..knowledge_seed import SeedDocument, chunk_markdown, load_seed_documents
from ..rag import ChromaKnowledgeBase, KnowledgeDocument, get_default_knowledge_base


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
VALID_INDEX_STATES = {"pending", "indexing", "indexed", "failed"}


class KnowledgeError(RuntimeError):
    pass


class DuplicateKnowledgeDocument(KnowledgeError):
    pass


class KnowledgeIndexError(KnowledgeError):
    pass


class KnowledgeDeleteError(KnowledgeError):
    pass


def _safe_error(exc: Exception) -> str:
    text = " ".join(str(exc).split())
    text = re.sub(
        r"(?i)(api[_-]?key|authorization|password|secret|token)\s*[=:]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        text,
    )
    return (text or exc.__class__.__name__)[:500]


def _safe_filename(filename: str) -> str:
    candidate = filename.strip()
    if (
        not candidate
        or "\x00" in candidate
        or PurePath(candidate).name != candidate
        or "/" in candidate
        or "\\" in candidate
    ):
        raise ValueError("Unsafe filename")
    return candidate


def document_dto(document: KnowledgeDocumentORM, *, include_content: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(document.id),
        "title": document.title,
        "source_name": document.source_name,
        "kind": document.kind,
        "vector_document_id": document.vector_document_id,
        "index_status": document.index_status,
        "chunk_count": document.chunk_count,
        "metadata": document.document_metadata or {},
        "error": document.error,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }
    if include_content:
        payload["content_excerpt"] = document.content_text[:1000]
    return payload


class KnowledgeService:
    def __init__(
        self,
        knowledge_base_factory: Callable[[], ChromaKnowledgeBase] = get_default_knowledge_base,
        collection_name: str | None = None,
    ) -> None:
        self._knowledge_base_factory = knowledge_base_factory
        self.collection_name = collection_name or os.getenv(
            "REQ2TEST_CHROMA_COLLECTION", "req2test_knowledge"
        )

    def _kb(self) -> ChromaKnowledgeBase:
        return self._knowledge_base_factory()

    def list(self, session: Session, *, page: int, page_size: int) -> dict[str, Any]:
        documents, total = repository.list_documents(session, page=page, page_size=page_size)
        statuses = repository.count_by_index_status(session)
        return {
            "items": [document_dto(item) for item in documents],
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": math.ceil(total / page_size) if total else 0,
            "indexed": statuses.get("indexed", 0),
            "needs_attention": total - statuses.get("indexed", 0),
        }

    def get(self, session: Session, document_id: uuid.UUID) -> KnowledgeDocumentORM | None:
        return repository.get_document(session, document_id)

    def upload(
        self,
        session: Session,
        *,
        filename: str,
        content_base64: str,
        title: str | None,
        kind: str,
    ) -> KnowledgeDocumentORM:
        safe_name = _safe_filename(filename)
        suffix = Path(safe_name).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise ValueError("Unsupported knowledge document type")
        try:
            raw = base64.b64decode(content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid base64 document content") from exc
        if len(raw) > MAX_UPLOAD_BYTES:
            raise OverflowError("Knowledge document exceeds 10 MB")
        if not raw:
            raise ValueError("Knowledge document is empty")
        text = load_document_bytes(raw, suffix).strip()
        if not text:
            raise ValueError("Knowledge document is empty")

        digest = hashlib.sha256(raw).hexdigest()
        vector_id = f"upload-{digest}"
        if repository.get_by_vector_reference(
            session, collection=self.collection_name, vector_document_id=vector_id
        ):
            raise DuplicateKnowledgeDocument("Knowledge document already exists")
        metadata = {"sha256": digest, "characters": len(text), "suffix": suffix}
        try:
            document = repository.create_document(
                session,
                title=(title or Path(safe_name).stem).strip()[:500],
                source_name=safe_name,
                kind=kind.strip()[:64] or "testing_rule",
                vector_collection=self.collection_name,
                vector_document_id=vector_id,
                content_text=text,
                metadata=metadata,
            )
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise DuplicateKnowledgeDocument("Knowledge document already exists") from exc
        return self._index(session, document)

    def _vector_documents(self, document: KnowledgeDocumentORM) -> list[KnowledgeDocument]:
        chunks = chunk_markdown(document.content_text)
        return [
            KnowledgeDocument(
                document_id=f"{document.vector_document_id}:chunk:{index:04d}",
                text=chunk,
                metadata={
                    "catalog_document_id": str(document.id),
                    "parent_document_id": document.vector_document_id,
                    "source": document.source_name,
                    "title": document.title,
                    "kind": document.kind,
                    "chunk_index": index,
                    "chunk_count": len(chunks),
                },
            )
            for index, chunk in enumerate(chunks, start=1)
        ]

    def _index(self, session: Session, document: KnowledgeDocumentORM) -> KnowledgeDocumentORM:
        repository.set_index_state(session, document, "indexing")
        session.commit()
        try:
            vectors = self._vector_documents(document)
            self._kb().delete_where("parent_document_id", document.vector_document_id)
            self._kb().upsert(vectors)
        except Exception as exc:  # noqa: BLE001 - external vector backend boundary
            session.rollback()
            document = repository.get_document(session, document.id)
            if document is not None:
                repository.set_index_state(session, document, "failed", error=_safe_error(exc))
                session.commit()
            raise KnowledgeIndexError("Knowledge indexing failed") from exc
        document = repository.get_document(session, document.id)
        if document is None:
            raise KnowledgeIndexError("Knowledge catalog entry disappeared during indexing")
        repository.set_index_state(session, document, "indexed", chunk_count=len(vectors))
        session.commit()
        return document

    def reindex(self, session: Session, document: KnowledgeDocumentORM) -> KnowledgeDocumentORM:
        return self._index(session, document)

    def delete(self, session: Session, document: KnowledgeDocumentORM) -> None:
        vectors = self._vector_documents(document)
        try:
            self._kb().delete_where("parent_document_id", document.vector_document_id)
        except Exception as exc:  # noqa: BLE001
            repository.set_index_state(
                session, document, "failed", error=f"Vector deletion failed: {_safe_error(exc)}"
            )
            session.commit()
            raise KnowledgeDeleteError("Knowledge vector deletion failed; catalog retained") from exc
        try:
            repository.delete_document(session, document)
            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            try:
                self._kb().upsert(vectors)
            except Exception as compensation_exc:  # noqa: BLE001
                restored = repository.get_document(session, document.id)
                if restored is not None:
                    repository.set_index_state(
                        session,
                        restored,
                        "failed",
                        error=f"Catalog delete and vector compensation failed: {_safe_error(compensation_exc)}",
                    )
                    session.commit()
            raise KnowledgeDeleteError("Knowledge catalog deletion failed; vector compensated") from exc

    def search(self, query: str, *, top_k: int) -> list[dict[str, Any]]:
        matches = self._kb().search(query, top_k=top_k)
        return [
            {
                "document_id": str(
                    (match.get("metadata") or {}).get("catalog_document_id")
                    or match.get("document_id")
                ),
                "vector_document_id": match.get("document_id"),
                "chunk_index": (match.get("metadata") or {}).get("chunk_index"),
                "source": (match.get("metadata") or {}).get("source"),
                "kind": (match.get("metadata") or {}).get("kind"),
                "text_excerpt": str(match.get("text") or "")[:500],
                "distance": match.get("distance"),
                "similarity": match.get("similarity"),
            }
            for match in matches[:top_k]
        ]

    def rebuild(self, session: Session) -> dict[str, int]:
        documents = repository.all_documents(session)
        for document in documents:
            repository.set_index_state(session, document, "indexing")
        session.commit()
        try:
            vectors = [vector for item in documents for vector in self._vector_documents(item)]
            count = self._kb().rebuild(vectors)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            for document in repository.all_documents(session):
                repository.set_index_state(session, document, "failed", error=_safe_error(exc))
            session.commit()
            raise KnowledgeIndexError("Knowledge rebuild failed") from exc
        for document in repository.all_documents(session):
            repository.set_index_state(
                session, document, "indexed", chunk_count=len(self._vector_documents(document))
            )
        session.commit()
        return {"indexed_documents": len(documents), "indexed_chunks": count}

    def seed(self, session: Session, *, directory: Path | None = None) -> dict[str, int]:
        """Create/update curated catalog rows and index them without duplicates."""

        created = updated = 0
        changed_ids: set[uuid.UUID] = set()
        catalog: list[KnowledgeDocumentORM] = []
        for seed in load_seed_documents(directory):
            document = repository.get_by_vector_reference(
                session,
                collection=self.collection_name,
                vector_document_id=seed.vector_document_id,
            )
            metadata = self._seed_metadata(seed)
            if document is None:
                document = repository.create_document(
                    session,
                    title=seed.title,
                    source_name=seed.source_name,
                    kind=seed.kind,
                    vector_collection=self.collection_name,
                    vector_document_id=seed.vector_document_id,
                    content_text=seed.content,
                    metadata=metadata,
                )
                created += 1
            elif document.document_metadata.get("sha256") != seed.sha256:
                document.title = seed.title
                document.source_name = seed.source_name
                document.kind = seed.kind
                document.content_text = seed.content
                document.document_metadata = metadata
                updated += 1
                changed_ids.add(document.id)
            catalog.append(document)
        session.commit()
        if created:
            rebuilt = self.rebuild(session)
            return {
                "documents": len(catalog),
                "created": created,
                "updated": updated,
                "indexed_chunks": rebuilt["indexed_chunks"],
            }
        expected_total = sum(
            len(self._vector_documents(document))
            for document in repository.all_documents(session)
        )
        if self._kb().count() != expected_total:
            rebuilt = self.rebuild(session)
            return {
                "documents": len(catalog),
                "created": created,
                "updated": updated,
                "indexed_chunks": rebuilt["indexed_chunks"],
            }
        indexed_chunks = 0
        for document in catalog:
            expected = len(self._vector_documents(document))
            if (
                document.index_status != "indexed"
                or document.chunk_count != expected
                or document.id in changed_ids
            ):
                self._index(session, document)
            indexed_chunks += document.chunk_count
        return {
            "documents": len(catalog),
            "created": created,
            "updated": updated,
            "indexed_chunks": indexed_chunks,
        }

    @staticmethod
    def _seed_metadata(seed: SeedDocument) -> dict[str, Any]:
        return {
            "builtin": True,
            "source": seed.source,
            "license": seed.license,
            "version": seed.version,
            "sha256": seed.sha256,
        }
