"""Command-line utilities for the persistent Req2Test RAG knowledge base."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .rag import ChromaKnowledgeBase, load_historical_case_documents, load_rule_documents


def _build_documents(root: Path):
    documents = []
    rule_path = root / "knowledge" / "testing_rules.md"
    case_path = root / "knowledge" / "historical_cases.jsonl"
    if rule_path.exists():
        documents.extend(load_rule_documents(rule_path))
    if case_path.exists():
        documents.extend(load_historical_case_documents(case_path))
    return documents


def main() -> None:
    parser = argparse.ArgumentParser(description="管理 Req2Test RAG 向量知识库")
    parser.add_argument("command", choices=["rebuild", "stats", "search"])
    parser.add_argument("--query", default="", help="search 命令的检索文本")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--persist-dir", default=".req2test/chroma")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    knowledge_base = ChromaKnowledgeBase(root / args.persist_dir)

    if args.command == "rebuild":
        count = knowledge_base.rebuild(_build_documents(root))
        print(json.dumps({"indexed_documents": count, **knowledge_base.stats()}, ensure_ascii=False, indent=2))
        return

    if args.command == "stats":
        print(json.dumps(knowledge_base.stats(), ensure_ascii=False, indent=2))
        return

    if not args.query.strip():
        parser.error("search 命令必须提供 --query")
    print(json.dumps(knowledge_base.search(args.query, top_k=args.top_k), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
