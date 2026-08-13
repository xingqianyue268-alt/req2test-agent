"""Curated, idempotent seed catalog for the product knowledge base."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SeedDocument:
    title: str
    source_name: str
    kind: str
    source: str
    license: str
    version: str
    content: str
    sha256: str

    @property
    def vector_document_id(self) -> str:
        return f"seed-{self.source_name.removesuffix('.md')}"


def default_seed_directory() -> Path:
    source_tree = Path(__file__).resolve().parents[2] / "knowledge_seed"
    return source_tree if source_tree.exists() else Path.cwd() / "knowledge_seed"


def load_seed_documents(directory: Path | None = None) -> list[SeedDocument]:
    root = directory or default_seed_directory()
    documents: list[SeedDocument] = []
    for path in sorted(root.glob("*.md")):
        raw = path.read_text(encoding="utf-8").strip()
        metadata, content = _parse_front_matter(raw)
        documents.append(
            SeedDocument(
                title=metadata.get("title", path.stem.replace("_", " ").title()),
                source_name=path.name,
                kind=metadata.get("category", "testing_rule"),
                source=metadata.get("source", "Req2Test curated knowledge"),
                license=metadata.get("license", "Original summary; source licenses apply"),
                version=metadata.get("version", "1.0"),
                content=content,
                sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            )
        )
    return documents


def _parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---\n"):
        return {}, raw
    end = raw.find("\n---\n", 4)
    if end < 0:
        return {}, raw
    metadata: dict[str, str] = {}
    for line in raw[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip().strip('"')
    return metadata, raw[end + 5 :].strip()


def chunk_markdown(text: str, *, max_chars: int = 1200) -> list[str]:
    """Split Markdown on headings, then bound oversized sections by paragraphs."""

    sections = re.split(r"(?=^##?\s)", text.strip(), flags=re.MULTILINE)
    chunks: list[str] = []
    for section in (item.strip() for item in sections if item.strip()):
        if len(section) <= max_chars:
            chunks.append(section)
            continue
        current = ""
        for paragraph in section.split("\n\n"):
            candidate = f"{current}\n\n{paragraph}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = paragraph
            else:
                current = candidate
        if current:
            chunks.append(current)
    return [chunk for chunk in chunks if chunk]
