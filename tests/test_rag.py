from pathlib import Path

from req2test.rag import ChromaKnowledgeBase, HashingEmbedder, KnowledgeDocument


def test_hashing_embedder_is_deterministic():
    embedder = HashingEmbedder(dimensions=64)
    first = embedder.embed("登录功能测试")
    second = embedder.embed("登录功能测试")
    assert first == second
    assert len(first) == 64


def test_chroma_upsert_and_search(tmp_path: Path):
    knowledge_base = ChromaKnowledgeBase(tmp_path / "chroma", collection_name="test_req2test")
    documents = [
        KnowledgeDocument(
            document_id="login-success",
            text="登录测试：输入有效账号和正确密码，点击登录后进入系统首页。",
            metadata={"kind": "historical_case", "module": "登录"},
        ),
        KnowledgeDocument(
            document_id="file-upload",
            text="文件上传测试：选择合法文件并提交，系统完成解析并展示成功反馈。",
            metadata={"kind": "historical_case", "module": "文件上传"},
        ),
    ]

    assert knowledge_base.upsert(documents) == 2
    assert knowledge_base.count() == 2

    matches = knowledge_base.search("用户使用正确账号密码登录", top_k=1)
    assert len(matches) == 1
    assert matches[0]["document_id"] == "login-success"
    assert matches[0]["metadata"]["kind"] == "historical_case"
