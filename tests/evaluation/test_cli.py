from __future__ import annotations

import json
import os
import subprocess
import sys

import req2test.evaluation.cli as cli_module
from req2test.evaluation.cli import run_evaluation_command


def test_demo_gate_passes_offline_and_prints_reproducibility_metadata(capsys, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-read-in-demo")
    exit_code = run_evaluation_command(
        [
            "--dataset",
            "evals/golden_demo.jsonl",
            "--mode",
            "demo",
            "--min-score",
            "80",
            "--seed",
            "42",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["overall_score"] >= 80
    assert payload["seed"] == 42
    assert len(payload["dataset_digest"]) == len(payload["prompt_digest"]) == 64
    assert "must-not-be-read-in-demo" not in str(payload)


def test_script_returns_nonzero_below_gate_without_api_key_dependency():
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_eval.py",
            "--dataset",
            "evals/golden_demo.jsonl",
            "--mode",
            "demo",
            "--min-score",
            "100",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    payload = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert payload["status"] == "failed"
    assert "api_key" not in completed.stdout.lower()


def test_invalid_dataset_returns_nonzero():
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_eval.py",
            "--dataset",
            "evals/not-registered.jsonl",
            "--mode",
            "demo",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert json.loads(completed.stderr)["status"] == "error"


def test_evaluation_execution_error_returns_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(
        cli_module,
        "evaluate_golden_dataset",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("evaluation execution unavailable token=do-not-print")
        ),
    )
    exit_code = run_evaluation_command(
        ["--dataset", "evals/golden_demo.jsonl", "--mode", "demo"]
    )
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "do-not-print" not in captured.err
    assert json.loads(captured.err)["status"] == "error"
