import base64

from fastapi.testclient import TestClient

from req2test.api import app
from req2test.demo_ui import DEMO_HTML


client = TestClient(app)


def test_root_and_demo_expose_unified_workbench():
    root = client.get("/")
    demo = client.get("/demo")
    assert root.status_code == 200
    assert demo.status_code == 200
    for marker in [
        "从需求文档到可执行测试",
        "AI 生成并评审测试用例",
        "测试用例",
        "需求拆分",
        "评审 & RAG",
        "执行结果",
    ]:
        assert marker in root.text
        assert marker in DEMO_HTML


def test_parse_text_document_for_workbench():
    content = "用户可以新增供应商，保存后供应商显示在列表中。".encode("utf-8")
    response = client.post(
        "/api/v1/documents/parse",
        json={
            "filename": "requirements.md",
            "content_base64": base64.b64encode(content).decode("ascii"),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["suffix"] == ".md"
    assert "新增供应商" in payload["text"]
    assert payload["characters"] > 0


def test_parse_document_rejects_unsupported_suffix():
    response = client.post(
        "/api/v1/documents/parse",
        json={
            "filename": "requirements.xlsx",
            "content_base64": base64.b64encode(b"test").decode("ascii"),
        },
    )
    assert response.status_code == 400
