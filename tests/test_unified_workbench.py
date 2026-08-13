import base64

from fastapi.testclient import TestClient

from req2test.api import app
from req2test.demo_ui import DEMO_HTML, render_demo_html


client = TestClient(app)


def test_root_redirects_to_real_workbench_route():
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 307
    assert root.headers["location"] == "/workbench"


def test_real_product_routes_share_shell_and_render_only_their_page():
    protected = client.get("/workbench", follow_redirects=False)
    assert protected.status_code == 307
    assert protected.headers["location"] == "/login?next=/workbench"
    workbench = client.get("/demo")
    workflow = client.get("/workflow")
    system = client.get("/system")
    assert [response.status_code for response in (workbench, workflow, system)] == [
        200,
        200,
        200,
    ]

    for response in (workbench, workflow, system):
        assert '<header class="site-nav">' in response.text
        assert 'href="/workbench"' in response.text
        assert 'href="/workflow"' in response.text
        assert 'href="/system"' in response.text
        assert "#workbench" not in response.text
        assert "hashchange" not in response.text

    assert 'data-view="workbench"' in workbench.text
    assert 'data-page="workbench"' in workbench.text
    assert 'data-page="workflow"' not in workbench.text
    assert 'data-page="system"' not in workbench.text
    assert 'data-workbench-stage="new"' in workbench.text
    assert 'data-workbench-stage="progress"' in workbench.text
    assert 'data-workbench-stage="results"' in workbench.text

    assert 'data-view="workflow"' in workflow.text
    assert 'data-page="workflow"' in workflow.text
    assert 'data-page="workbench"' not in workflow.text
    assert 'data-page="system"' not in workflow.text
    assert "ONE SYSTEM." in workflow.text
    assert "engineering-flow" in workflow.text

    assert 'data-view="system"' in system.text
    assert 'data-page="system"' in system.text
    assert 'data-page="workbench"' not in system.text
    assert 'data-page="workflow"' not in system.text
    assert "RAG Knowledge Base" in system.text
    assert "WebSocket" in system.text


def test_workbench_preserves_existing_generation_and_result_features():
    root = client.get("/demo")
    for marker in [
        "FROM",
        "REQUIREMENT",
        "TO REAL TEST.",
        "GENERATE TESTS",
        "测试用例",
        "需求拆分",
        "AI 评审 &amp; RAG",
        "执行结果",
        '<span class="en-ui">WORKBENCH</span><span class="zh-ui">/ 工作台</span>',
        '<span class="en-ui">HOW IT WORKS</span><span class="zh-ui">/ 工作流程</span>',
        '<span class="en-ui">SYSTEM</span><span class="zh-ui">/ 系统状态</span>',
        'body data-view="workbench"',
        'data-stage-panel="new"',
        'data-stage-panel="progress"',
        'data-stage-panel="results"',
        "showWorkbenchStage('progress')",
        "showWorkbenchStage('results')",
        '--en:Inter,-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif',
        '--copy:"Times New Roman",Times,serif',
    ]:
        assert marker in root.text
        assert marker in DEMO_HTML

    assert render_demo_html("workbench") == DEMO_HTML


def test_login_and_register_pages_match_editorial_auth_experience():
    login = client.get("/login")
    register = client.get("/register")
    assert login.status_code == register.status_code == 200
    assert "WELCOME\nBACK." in login.text
    assert "LOGIN / 登录" in login.text
    assert "CREATE ACCOUNT / 注册账户" in login.text
    assert "CREATE\nACCOUNT." in register.text
    assert "CONFIRM PASSWORD" in register.text
    assert "localStorage" not in login.text
    assert "req2test_access_token" not in login.text


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
