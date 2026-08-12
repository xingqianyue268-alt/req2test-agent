"""Knowledge retrieval for testing rules and historical test cases.

Vector retrieval is preferred when Chroma is available. The original local
character-bigram retriever remains as a zero-dependency fallback so demo mode
continues to work in restricted environments.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path


def split_markdown_sections(text: str) -> list[str]:
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


def _tokens(text: str) -> list[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    chinese_bigrams = [normalized[index : index + 2] for index in range(len(normalized) - 1)]
    words = re.findall(r"[a-z0-9_+-]{2,}", text.lower())
    return chinese_bigrams + words


def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    shared = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


class LocalRuleRetriever:
    """Lightweight retriever used as an offline fallback."""

    def __init__(self, sections: list[str]):
        if not sections:
            raise ValueError("知识库不能为空")
        self.sections = sections
        self.vectors = [Counter(_tokens(section)) for section in sections]

    @classmethod
    def from_markdown(cls, path: str | Path) -> "LocalRuleRetriever":
        text = Path(path).read_text(encoding="utf-8")
        return cls(split_markdown_sections(text))

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        query_vector = Counter(_tokens(query))
        ranked = sorted(
            zip(self.sections, self.vectors),
            key=lambda item: _cosine_similarity(query_vector, item[1]),
            reverse=True,
        )
        return [section for section, _ in ranked[: max(1, top_k)]]


class HybridKnowledgeRetriever:
    """Prefer persistent Chroma vector search and fall back to local rules."""

    def __init__(self, rule_path: str | Path):
        self.rule_path = Path(rule_path)
        self.local = LocalRuleRetriever.from_markdown(self.rule_path)
        self.backend = "local"

    def retrieve(self, query: str, top_k: int = 4) -> list[str]:
        try:
            from .rag import get_default_knowledge_base

            knowledge_base = get_default_knowledge_base()
            matches = knowledge_base.search(query, top_k=top_k)
            if matches:
                self.backend = "chroma"
                return [self._format_match(match) for match in matches]
        except Exception:  # noqa: BLE001 - vector search is an optional enhancement
            self.backend = "local"

        return self.local.retrieve(query, top_k=min(top_k, 3))

    @staticmethod
    def _format_match(match: dict) -> str:
        metadata = match.get("metadata", {})
        kind = metadata.get("kind", "knowledge")
        source = metadata.get("source", "unknown")
        similarity = match.get("similarity")
        similarity_text = "" if similarity is None else f"，相似度={similarity:.3f}"
        return f"[RAG:{kind}｜来源={source}{similarity_text}]\n{match.get('text', '')}"
