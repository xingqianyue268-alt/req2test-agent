"""P0 target authorization regressions; all actual requests stay on loopback."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from req2test.config import LLMSettings
from req2test.execution_models import ExecutionConfig, HttpTestSpec
from req2test.http_tool import HttpApiTestTool
from req2test.models import ReviewReport, WorkflowResult
from req2test.pytest_runner import PytestRunnerTool, render_pytest_module
from req2test.tool_calling import execute_with_tools


@pytest.fixture(scope="module")
def target():
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            if self.path.startswith("/redirect/"):
                _, _, code, kind = self.path.split("/")
                location = {
                    "other": f"http://127.0.0.1:{self.server.server_port}/final",
                    "same": f"http://localhost:{self.server.server_port}/final",
                    "relative": "/final",
                    "loop": self.path,
                }[kind]
                self.send_response(int(code))
                self.send_header("Location", location)
            else:
                self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://localhost:{server.server_port}", hits
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


@pytest.fixture(autouse=True)
def restricted_hosts(monkeypatch):
    monkeypatch.setenv("REQ2TEST_ALLOW_REMOTE_EXECUTION", "false")
    monkeypatch.setenv("REQ2TEST_EXECUTION_ALLOWED_HOSTS", "localhost")


@pytest.mark.parametrize("engine", ["http", "pytest"])
@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("kind", ["other", "same", "relative", "loop"])
def test_redirects_are_observed_without_following(target, engine, code, kind):
    base, hits = target
    hits.clear()
    path = f"/redirect/{code}/{kind}"
    spec = HttpTestSpec(case_id="REDIRECT", name="redirect", path=path, expected_status=code)
    if engine == "http":
        result = HttpApiTestTool(base).invoke(spec)
        assert result.status_code == code
    else:
        result = PytestRunnerTool().invoke([spec], base)
    assert result.passed
    assert hits == [path], "No second hop, even when the new host would be allowed"


@pytest.mark.parametrize("http,pytest_enabled", [(True, False), (False, True), (True, True)])
def test_common_entry_rejects_before_dispatch(monkeypatch, http, pytest_enabled):
    calls = []
    monkeypatch.setattr("req2test.pytest_runner.subprocess.run", lambda *a, **k: calls.append(1))
    workflow = WorkflowResult(
        requirements=[], test_cases=[], review=ReviewReport(score=100, coverage_rate=1)
    )
    config = ExecutionConfig(
        enabled=True,
        base_url="http://127.0.0.1:1",
        run_http_tool=http,
        run_pytest=pytest_enabled,
        api_specs=[HttpTestSpec(case_id="ONE", name="one", path="/")],
    )
    with pytest.raises(ValueError, match="白名单"):
        execute_with_tools("", workflow, LLMSettings(), config)
    assert not calls


@pytest.mark.parametrize(
    "base", ["http://127.0.0.1:1", "http://user:pass@localhost", "file:///tmp/x"]
)
def test_direct_runner_rejects_before_subprocess(monkeypatch, base):
    calls = []
    monkeypatch.setattr("req2test.pytest_runner.subprocess.run", lambda *a, **k: calls.append(1))
    with pytest.raises(ValueError):
        PytestRunnerTool().invoke([HttpTestSpec(case_id="ONE", name="one", path="/")], base)
    assert not calls


def test_rendered_module_also_revalidates_current_policy(monkeypatch):
    spec = HttpTestSpec(case_id="ONE", name="one", path="/")
    source = render_pytest_module([spec], "http://localhost:8000")
    monkeypatch.setenv("REQ2TEST_EXECUTION_ALLOWED_HOSTS", "api")
    calls = []
    monkeypatch.setattr("httpx.Client", lambda **kwargs: calls.append(kwargs))
    with pytest.raises(ValueError, match="白名单"):
        namespace = {}
        exec(compile(source, "<generated>", "exec"), namespace)  # noqa: S102 - fixed local template
        namespace["test_generated_http_case"](spec.model_dump())
    assert not calls


def test_explicit_remote_opt_in_is_preserved_without_contact(monkeypatch):
    monkeypatch.setenv("REQ2TEST_ALLOW_REMOTE_EXECUTION", "true")
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")

    monkeypatch.setattr("req2test.pytest_runner.subprocess.run", fake_run)
    result = PytestRunnerTool().invoke(
        [HttpTestSpec(case_id="ONE", name="one", path="/")], "https://approved.example.test"
    )
    assert result.passed and len(calls) == 1
