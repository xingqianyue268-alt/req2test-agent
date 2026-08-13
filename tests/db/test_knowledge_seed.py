from __future__ import annotations

from req2test.db.repositories import knowledge_documents
from req2test.knowledge_seed import load_seed_documents
from req2test.rag import ChromaKnowledgeBase
from req2test.services.knowledge_service import KnowledgeService


def test_seed_initialization_is_indexed_and_idempotent(db_session, tmp_path):
    kb = ChromaKnowledgeBase(tmp_path / "chroma", collection_name="seed_idempotency")
    service = KnowledgeService(lambda: kb, collection_name=kb.collection_name)

    first = service.seed(db_session)
    second = service.seed(db_session)
    documents = knowledge_documents.all_documents(db_session)

    assert first["documents"] == len(load_seed_documents()) == 13
    assert first["created"] == 13
    assert second["created"] == second["updated"] == 0
    assert second["indexed_chunks"] == first["indexed_chunks"] == kb.count()
    assert all(item.index_status == "indexed" for item in documents)
    assert sum(item.chunk_count for item in documents) == kb.count()
    assert all(item.document_metadata["source"] for item in documents)
    assert all(item.document_metadata["license"] for item in documents)


def test_seed_rag_search_delete_and_rebuild(db_session, tmp_path):
    kb = ChromaKnowledgeBase(tmp_path / "chroma", collection_name="seed_lifecycle")
    service = KnowledgeService(lambda: kb, collection_name=kb.collection_name)
    seeded = service.seed(db_session)

    matches = service.search("401 token authentication 认证失败", top_k=3)
    assert matches
    assert any(item["source"] == "11_authentication_authorization.md" for item in matches)
    assert all(item["similarity"] is not None for item in matches)
    assert all(item["text_excerpt"] for item in matches)

    document = next(
        item
        for item in knowledge_documents.all_documents(db_session)
        if item.source_name == "11_authentication_authorization.md"
    )
    original_chunks = document.chunk_count
    service.delete(db_session, document)
    assert kb.count() == seeded["indexed_chunks"] - original_chunks

    rebuilt = service.rebuild(db_session)
    assert rebuilt["indexed_documents"] == 12
    assert rebuilt["indexed_chunks"] == kb.count()


def test_workbench_retriever_recalls_catalog_seed(db_session, tmp_path, monkeypatch):
    import req2test.rag as rag_module
    from req2test.rag_node import retrieve_context_node

    kb = ChromaKnowledgeBase(tmp_path / "chroma", collection_name="seed_workbench")
    service = KnowledgeService(lambda: kb, collection_name=kb.collection_name)
    service.seed(db_session)
    monkeypatch.setattr(rag_module, "get_default_knowledge_base", lambda: kb)

    result = retrieve_context_node(
        {"requirement_text": "API 返回 422 时检查 OpenAPI schema 契约不匹配"}
    )

    assert result["retrieval_backend"] == "chroma"
    assert any("来源=08_api_testing.md" in item for item in result["retrieved_context"])
