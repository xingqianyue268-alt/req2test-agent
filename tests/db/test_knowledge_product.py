from __future__ import annotations

import base64
import uuid

from fastapi.testclient import TestClient

import req2test.api as api_module
from req2test.db.repositories import knowledge_documents, users
from req2test.db.session import get_db
from req2test.rag import KnowledgeDocument
from req2test.security.passwords import hash_password
from req2test.services.knowledge_service import KnowledgeService


PASSWORD = "correct horse battery staple"


class FakeKnowledgeBase:
    collection_name = "test_product_knowledge"

    def __init__(self):
        self.documents: dict[str, KnowledgeDocument] = {}
        self.fail_upsert = False
        self.fail_delete = False

    def upsert(self, documents):
        if self.fail_upsert:
            raise RuntimeError("vector backend unavailable secret=never-log-this")
        self.documents.update({item.document_id: item for item in documents})
        return len(documents)

    def delete(self, document_id):
        if self.fail_delete:
            raise RuntimeError("vector delete unavailable")
        self.documents.pop(document_id, None)

    def search(self, query, top_k=4):
        return [
            {
                "document_id": item.document_id,
                "text": item.text,
                "metadata": item.metadata,
                "distance": index / 10,
                "similarity": 1 - index / 10,
            }
            for index, item in enumerate(list(self.documents.values())[:top_k], start=1)
            if query.strip()
        ]

    def rebuild(self, documents):
        if self.fail_upsert:
            raise RuntimeError("rebuild unavailable")
        self.documents = {item.document_id: item for item in documents}
        return len(documents)


def _client(db_session, monkeypatch):
    def override_db():
        yield db_session

    fake = FakeKnowledgeBase()
    service = KnowledgeService(lambda: fake)
    api_module.app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(api_module, "knowledge_service", service)
    return TestClient(api_module.app), fake


def _user(db_session, email, role="user"):
    record = users.create_user(
        db_session, email=email, password_hash=hash_password(PASSWORD), role=role
    )
    db_session.commit()
    return record


def _login(client, email):
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200


def _upload(filename="rules.md", text="# API Rules\n\nA contract mismatch is HTTP 422.", **extra):
    return {
        "filename": filename,
        "content_base64": base64.b64encode(text.encode()).decode(),
        "kind": "testing_rule",
        **extra,
    }


def test_knowledge_rbac_upload_list_detail_search_top_k_and_ui(db_session, monkeypatch):
    client, fake = _client(db_session, monkeypatch)
    user = _user(db_session, "knowledge-user@example.com")
    admin = _user(db_session, "knowledge-admin@example.com", role="admin")
    try:
        _login(client, user.email)
        assert client.get("/knowledge").status_code == 200
        assert client.get("/api/v1/knowledge/documents").json()["items"] == []
        assert client.post("/api/v1/knowledge/documents", json=_upload()).status_code == 403
        assert client.post(
            "/api/v1/knowledge/search", json={"query": "contract", "top_k": 21}
        ).status_code == 422
        client.post("/api/v1/auth/logout")

        _login(client, admin.email)
        created = client.post("/api/v1/knowledge/documents", json=_upload())
        assert created.status_code == 201
        body = created.json()
        assert body["index_status"] == "indexed"
        assert body["content_excerpt"].startswith("# API Rules")
        assert body["vector_document_id"] in fake.documents
        document_id = body["id"]
        detail = client.get(f"/api/v1/knowledge/documents/{document_id}")
        assert detail.status_code == 200
        assert "content_text" not in detail.json()
        assert client.post("/api/v1/knowledge/documents", json=_upload()).status_code == 409
        client.post("/api/v1/auth/logout")

        _login(client, user.email)
        search = client.post(
            "/api/v1/knowledge/search", json={"query": "422 contract", "top_k": 1}
        )
        assert search.status_code == 200
        match = search.json()["items"][0]
        assert match["document_id"] == document_id
        assert match["source"] == "rules.md"
        assert match["kind"] == "testing_rule"
        assert len(match["text_excerpt"]) <= 500
        assert len(search.json()["items"]) == 1
    finally:
        api_module.app.dependency_overrides.clear()


def test_index_failure_reindex_delete_consistency_and_rebuild(db_session, monkeypatch, caplog):
    client, fake = _client(db_session, monkeypatch)
    admin = _user(db_session, "knowledge-ops@example.com", role="admin")
    try:
        _login(client, admin.email)
        fake.fail_upsert = True
        failed = client.post(
            "/api/v1/knowledge/documents", json=_upload("failure.txt", "useful rule")
        )
        assert failed.status_code == 502
        row = knowledge_documents.list_documents(db_session)[0][0]
        assert row.index_status == "failed"
        assert "secret=[REDACTED]" in row.error
        assert "never-log-this" not in row.error
        assert "secret=never-log-this" not in caplog.text

        fake.fail_upsert = False
        reindexed = client.post(f"/api/v1/knowledge/documents/{row.id}/reindex")
        assert reindexed.status_code == 200
        assert reindexed.json()["index_status"] == "indexed"
        assert row.vector_document_id in fake.documents

        assert client.post("/api/v1/knowledge/rebuild").json() == {"indexed_documents": 1}
        fake.fail_delete = True
        failed_delete = client.delete(f"/api/v1/knowledge/documents/{row.id}")
        assert failed_delete.status_code == 502
        db_session.expire_all()
        retained = knowledge_documents.get_document(db_session, row.id)
        assert retained is not None and retained.index_status == "failed"

        fake.fail_delete = False
        assert client.delete(f"/api/v1/knowledge/documents/{row.id}").status_code == 204
        assert knowledge_documents.get_document(db_session, row.id) is None
        assert row.vector_document_id not in fake.documents
    finally:
        api_module.app.dependency_overrides.clear()


def test_upload_validation_malicious_unsupported_oversize_and_empty(db_session, monkeypatch):
    client, _ = _client(db_session, monkeypatch)
    admin = _user(db_session, "knowledge-validation@example.com", role="admin")
    try:
        _login(client, admin.email)
        assert client.post(
            "/api/v1/knowledge/documents", json=_upload("../../secret.md")
        ).status_code == 400
        assert client.post(
            "/api/v1/knowledge/documents", json=_upload("rules.exe")
        ).status_code == 400
        assert client.post(
            "/api/v1/knowledge/documents",
            json={"filename": "empty.txt", "content_base64": base64.b64encode(b"").decode()},
        ).status_code == 422
        assert client.post(
            "/api/v1/knowledge/documents",
            json={"filename": "blank.txt", "content_base64": base64.b64encode(b"  \n").decode()},
        ).status_code == 400
        oversized = base64.b64encode(b"x" * (10 * 1024 * 1024 + 1)).decode()
        assert client.post(
            "/api/v1/knowledge/documents",
            json={"filename": "large.txt", "content_base64": oversized},
        ).status_code == 413
        assert knowledge_documents.list_documents(db_session)[1] == 0
    finally:
        api_module.app.dependency_overrides.clear()


def test_knowledge_document_not_found_contracts(db_session, monkeypatch):
    client, _ = _client(db_session, monkeypatch)
    admin = _user(db_session, "knowledge-missing@example.com", role="admin")
    missing = uuid.uuid4()
    try:
        _login(client, admin.email)
        assert client.get(f"/api/v1/knowledge/documents/{missing}").status_code == 404
        assert client.post(f"/api/v1/knowledge/documents/{missing}/reindex").status_code == 404
        assert client.delete(f"/api/v1/knowledge/documents/{missing}").status_code == 404
    finally:
        api_module.app.dependency_overrides.clear()
