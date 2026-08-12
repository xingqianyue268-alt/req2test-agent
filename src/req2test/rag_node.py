"""LangGraph retrieval node backed by the hybrid RAG retriever."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .retrieval import HybridKnowledgeRetriever


def retrieve_context_node(state: dict[str, Any]) -> dict[str, Any]:
    """Retrieve relevant testing rules and historical cases for the requirement."""

    knowledge_path = Path(__file__).resolve().parents[2] / "knowledge" / "testing_rules.md"
    if not knowledge_path.exists():
        knowledge_path = Path.cwd() / "knowledge" / "testing_rules.md"

    retriever = HybridKnowledgeRetriever(knowledge_path)
    context = retriever.retrieve(str(state["requirement_text"]), top_k=4)
    return {
        "retrieved_context": context,
        "retrieval_backend": retriever.backend,
    }
