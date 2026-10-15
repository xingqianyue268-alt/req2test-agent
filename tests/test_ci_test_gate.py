"""Exercise real pytest exit codes and retained XML, including intentional failure."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "body,passed,failed,skipped",
    [("assert True", 1, 0, 0), ("assert False", 0, 1, 0), ('pytest.skip("fixture skip")', 0, 0, 1)],
)
def test_ci_gate_uses_real_report_and_never_hides_failure(tmp_path, body, passed, failed, skipped):
    test = tmp_path / "test_probe.py"
    test.write_text("import pytest\ndef test_probe():\n    " + body + "\n")
    report, summary = tmp_path / "pytest.xml", tmp_path / "summary.json"
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(test), "--junitxml=" + str(report)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    (tmp_path / "pytest.log").write_text(result.stdout + result.stderr)
    gate = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci_test_gate.py"),
            "--report",
            str(report),
            "--output",
            str(summary),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    value = json.loads(summary.read_text())
    assert (value["passed"], value["failed"], value["skipped"]) == (passed, failed, skipped)
    assert (gate.returncode == 0) == bool(passed)
    assert report.exists() and (tmp_path / "pytest.log").exists()
    if failed:
        assert result.returncode == 1


def test_gate_missing_xml_and_ci_always_upload(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci_test_gate.py"),
            "--report",
            str(tmp_path / "absent.xml"),
            "--output",
            str(tmp_path / "summary.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert json.loads((tmp_path / "summary.json").read_text())["status"] == "report_unavailable"
    workflow = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())
    steps = workflow["jobs"]["test"]["steps"]
    upload = next(s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@"))
    assert upload["if"] == "always()" and upload["with"]["if-no-files-found"] == "error"
    assert not any(s.get("continue-on-error", False) for s in steps)


def test_preflight_environment_failure_separate_and_no_credentials(tmp_path):
    env = {
        **os.environ,
        "REQ2TEST_TEST_DATABASE_URL": "postgresql+psycopg://synthetic:PRIVATE_SENTINEL@127.0.0.1:1/missing",
    }
    output = tmp_path / "environment.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci_test_gate.py"),
            "--preflight",
            "--output",
            str(output),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 1
    assert json.loads(output.read_text())["status"] == "environment_unavailable"
    assert "PRIVATE_SENTINEL" not in output.read_text() + result.stdout + result.stderr
