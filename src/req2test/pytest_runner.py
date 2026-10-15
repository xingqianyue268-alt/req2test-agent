"""Safe-ish Pytest runner that executes generated HTTP checks in a temporary directory.

The runner does not accept arbitrary Python source through the public API. It only
renders a fixed pytest template from validated HttpTestSpec objects, which keeps
the demo useful without turning the service into a general remote-code endpoint.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .execution_models import HttpExecutionResult, HttpTestSpec, PytestExecutionResult
from .security.execution import validate_execution_target
from .security.redaction import redact_text


def render_pytest_module(
    specs: list[HttpTestSpec],
    base_url: str,
    timeout_seconds: float = 8.0,
    verify_tls: bool = True,
    replay_results: dict[str, dict] | None = None,
) -> str:
    base_url = validate_execution_target(base_url)
    payload = [spec.model_dump() for spec in specs]
    payload_json = json.dumps(payload, ensure_ascii=False)
    replay_json = json.dumps(replay_results or {}, ensure_ascii=False)
    return f'''"""Auto-generated fixed template; no user Python. Live transport uses httpx.Client."""
import json
from pathlib import Path

import pytest
from req2test.execution_models import HttpTestSpec, HttpExecutionResult
from req2test.http_tool import HttpApiTestTool
from req2test.security.execution import validate_execution_target

BASE_URL = validate_execution_target({base_url!r})
SPECS = json.loads({payload_json!r})
REPLAY = json.loads({replay_json!r})
# Live HttpApiTestTool uses httpx.Client with follow_redirects=False.
TOOL = HttpApiTestTool(BASE_URL, timeout_seconds={float(timeout_seconds)!r}, verify_tls={bool(verify_tls)!r})


@pytest.mark.parametrize("spec", SPECS, ids=[item["case_id"] for item in SPECS])
def test_generated_http_case(spec):
    if spec["case_id"] in REPLAY:
        result = HttpExecutionResult.model_validate(REPLAY[spec["case_id"]])
        result.execution_mode = "replayed_http_result"
        result.duration_ms = 0.0  # No second network request; original time belongs to HTTP.
    else:
        result = TOOL.invoke(HttpTestSpec.model_validate(spec))
    result.executor = "pytest"
    # Append each sanitized record before assertion: later failures/timeouts keep earlier evidence.
    with Path(__file__).with_name("case-results.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(result.model_dump_json() + "\\n")
    assert result.passed, "; ".join(result.failures)
'''


def _count_summary(output: str, label: str) -> int:
    matches = re.findall(rf"(\d+)\s+{label}", output)
    return int(matches[-1]) if matches else 0


class PytestRunnerTool:
    """Render validated API specs into pytest and execute them with a hard timeout."""

    name = "pytest_runner"

    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    def invoke(
        self,
        specs: list[HttpTestSpec],
        base_url: str,
        request_timeout_seconds: float = 8.0,
        verify_tls: bool = True,
        replay_results: dict[str, dict] | None = None,
    ) -> PytestExecutionResult:
        base_url = validate_execution_target(base_url)
        if not specs:
            return PytestExecutionResult(
                passed=True,
                exit_code=0,
                duration_ms=0.0,
                stdout="没有可执行 HTTP 用例，已跳过 Pytest。",
                generated_test_file=None,
            )

        source = render_pytest_module(
            specs,
            base_url=base_url,
            timeout_seconds=request_timeout_seconds,
            verify_tls=verify_tls,
            replay_results=replay_results,
        )
        started = time.perf_counter()

        with tempfile.TemporaryDirectory(prefix="req2test-pytest-") as temp_dir:
            test_path = Path(temp_dir) / "test_req2test_generated.py"
            test_path.write_text(source, encoding="utf-8")

            def case_results():
                path = Path(temp_dir) / "case-results.jsonl"
                results = []
                if path.exists():
                    for line in path.read_text(encoding="utf-8").splitlines():
                        try:
                            results.append(HttpExecutionResult.model_validate_json(line))
                        except ValueError:
                            # An interrupted final write cannot turn a run into success.
                            continue
                return results

            env = os.environ.copy()
            env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
            env.pop("PYTEST_ADDOPTS", None)
            env.pop("PYTEST_PLUGINS", None)
            env["PYTHONPATH"] = os.pathsep.join(
                [str(Path(__file__).resolve().parents[1]), env.get("PYTHONPATH", "")]
            )
            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "--assert=plain",
                        "--tb=short",
                        str(test_path),
                    ],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    env=env,
                    check=False,
                )
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                combined = f"{completed.stdout}\n{completed.stderr}"
                passed_count = _count_summary(combined, "passed")
                failed_count = _count_summary(combined, "failed")
                error_count = _count_summary(combined, "error") + _count_summary(combined, "errors")
                return PytestExecutionResult(
                    passed=completed.returncode == 0,
                    exit_code=completed.returncode,
                    duration_ms=duration_ms,
                    passed_count=passed_count,
                    failed_count=failed_count,
                    error_count=error_count,
                    stdout=redact_text(completed.stdout)[-8000:],
                    stderr=redact_text(completed.stderr)[-4000:],
                    generated_test_file=test_path.name,
                    case_results=case_results(),
                )
            except subprocess.TimeoutExpired as exc:
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                stdout = (
                    exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                )
                stderr = (
                    exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                )
                return PytestExecutionResult(
                    passed=False,
                    exit_code=124,
                    duration_ms=duration_ms,
                    error_count=1,
                    stdout=redact_text(stdout)[-8000:],
                    stderr=(redact_text(stderr) + f"\nPytest 超过 {self.timeout_seconds}s 被终止")[
                        -4000:
                    ],
                    generated_test_file=test_path.name,
                    case_results=case_results(),
                )
