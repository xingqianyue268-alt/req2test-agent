"""Persistent RAG knowledge base backed by Chroma.

The module stores testing rules and historical test cases in a local Chroma
collection. To keep demo mode reproducible without an external embedding API,
it uses a deterministic hashing embedder over Chinese character bigrams and
English tokens. The vector database can later be switched to a model-based
embedding implementation without changing the workflow-facing API.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


@dataclass(slots=True)
class KnowledgeDocument:
    """One retrievable knowledge item."""

    document_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _tokens(text: str) -> list[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    chinese_bigrams = [normalized[index : index + 2] for index in range(len(normalized) - 1)]
    words = re.findall(r"[a-z0-9_+.-]{2,}", text.lower())
    return chinese_bigrams + words


class HashingEmbedder:
    """Small deterministic embedder suitable for offline demos and tests."""

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions < 32:
            raise ValueError("向量维度至少为 32")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector

    def embed_many(self, texts: Iterable[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _split_markdown_sections(text: str) -> list[str]:
    sections: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    return [section for section in sections if len(section) >= 20]


def load_rule_documents(path: str | Path) -> list[KnowledgeDocument]:
    rule_path = Path(path)
    sections = _split_markdown_sections(rule_path.read_text(encoding="utf-8"))
    documents: list[KnowledgeDocument] = []
    for index, section in enumerate(sections, start=1):
        digest = hashlib.sha1(section.encode("utf-8")).hexdigest()[:12]
        documents.append(
            KnowledgeDocument(
                document_id=f"rule-{index:03d}-{digest}",
                text=section,
                metadata={"kind": "testing_rule", "source": rule_path.name},
            )
        )
    return documents


def load_historical_case_documents(path: str | Path) -> list[KnowledgeDocument]:
    case_path = Path(path)
    if not case_path.exists():
        return []

    documents: list[KnowledgeDocument] = []
    for line_number, raw_line in enumerate(case_path.read_text(encoding="utf-8").splitlines(), start=1):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        payload = json.loads(raw_line)
        title = str(payload.get("title", "历史测试用例"))
        module = str(payload.get("module", "通用模块"))
        source_requirement = str(payload.get("source_requirement", ""))
        preconditions = payload.get("preconditions", [])
        steps = payload.get("steps", [])
        expected = payload.get("expected", [])
        text = (
            f"历史测试用例：{title}\n"
            f"模块：{module}\n"
            f"来源需求：{source_requirement}\n"
            f"前置条件：{'；'.join(map(str, preconditions))}\n"
            f"操作步骤：{'；'.join(map(str, steps))}\n"
            f"预期结果：{'；'.join(map(str, expected))}"
        )
        raw_id = str(payload.get("case_id", f"line-{line_number}"))
        documents.append(
            KnowledgeDocument(
                document_id=f"case-{raw_id}",
                text=text,
                metadata={
                    "kind": "historical_case",
                    "source": case_path.name,
                    "module": module,
                    "case_id": raw_id,
                },
            )
        )
    return documents


def _normalize_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    normalized: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)):
            normalized[key] = value
        elif value is not None:
            normalized[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return normalized


class ChromaKnowledgeBase:
    """Persistent vector store for testing rules and historical cases."""

    def __init__(
        self,
        persist_directory: str | Path,
        collection_name: str = "req2test_knowledge",
        embedder: HashingEmbedder | None = None,
    ) -> None:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - exercised only without optional dependency
            raise RuntimeError("未安装 chromadb，无法启用向量知识库") from exc

        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self.embedder = embedder or HashingEmbedder()
        self.client = chromadb.PersistentClient(path=str(self.persist_directory))
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Req2Test testing rules and historical test cases"},
        )

    def upsert(self, documents: list[KnowledgeDocument]) -> int:
        if not documents:
            return 0
        texts = [document.text for document in documents]
        self.collection.upsert(
            ids=[document.document_id for document in documents],
            documents=texts,
            embeddings=self.embedder.embed_many(texts),
            metadatas=[_normalize_metadata(document.metadata) for document in documents],
        )
        return len(documents)

    def search(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        query = query.strip()
        if not query or self.collection.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[self.embedder.embed(query)],
            n_results=max(1, min(top_k, self.collection.count())),
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        output: list[dict[str, Any]] = []
        for document_id, text, metadata, distance in zip(ids, documents, metadatas, distances):
            output.append(
                {
                    "document_id": document_id,
                    "text": text or "",
                    "metadata": metadata or {},
                    "distance": distance,
                    # Chroma's default squared-L2 distance over normalized vectors
                    # maps back to cosine similarity as 1 - distance / 2.
                    "similarity": None
                    if distance is None
                    else max(0.0, min(1.0, 1.0 - float(distance) / 2.0)),
                }
            )
        return output

    def count(self) -> int:
        return self.collection.count()

    def get(self, document_id: str) -> dict[str, Any] | None:
        result = self.collection.get(
            ids=[document_id], include=["documents", "metadatas"]
        )
        ids = result.get("ids", [])
        if not ids:
            return None
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        return {
            "document_id": ids[0],
            "text": documents[0] if documents else "",
            "metadata": metadatas[0] if metadatas else {},
        }

    def delete(self, document_id: str) -> None:
        self.collection.delete(ids=[document_id])

    def delete_where(self, metadata_key: str, value: str) -> None:
        self.collection.delete(where={metadata_key: value})

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "chroma",
            "collection": self.collection_name,
            "documents": self.count(),
            "persist_directory": str(self.persist_directory),
            "embedding": f"hashing-{self.embedder.dimensions}",
        }

    def rebuild(self, documents: list[KnowledgeDocument]) -> int:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:  # noqa: BLE001 - collection may not exist yet
            pass
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "Req2Test testing rules and historical test cases"},
        )
        return self.upsert(documents)

    def seed_default_documents(self, force: bool = False) -> int:
        if self.count() > 0 and not force:
            return 0
        root = _project_root()
        rule_path = root / "knowledge" / "testing_rules.md"
        case_path = root / "knowledge" / "historical_cases.jsonl"
        documents = load_rule_documents(rule_path) if rule_path.exists() else []
        documents.extend(load_historical_case_documents(case_path))
        if force:
            return self.rebuild(documents)
        return self.upsert(documents)


@lru_cache(maxsize=1)
def get_default_knowledge_base() -> ChromaKnowledgeBase:
    persist_directory = Path(os.getenv("REQ2TEST_CHROMA_DIR", ".req2test/chroma"))
    if not persist_directory.is_absolute():
        persist_directory = Path.cwd() / persist_directory
    collection_name = os.getenv("REQ2TEST_CHROMA_COLLECTION", "req2test_knowledge")
    return ChromaKnowledgeBase(persist_directory, collection_name=collection_name)
