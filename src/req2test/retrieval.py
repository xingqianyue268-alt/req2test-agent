"""A lightweight local retriever for testing rules.

The implementation deliberately avoids an embedding service so demo mode can run
without an API key. It uses character bigrams plus cosine similarity, which is
sufficient for short Chinese testing guidelines.
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
