"""Command-line regression gate for Golden Evaluation Datasets."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ..config import GenerationConfig, LLMSettings
from .dataset import load_golden_dataset
from .engine import evaluate_golden_dataset
from .safety import safe_failure_reason


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a reproducible Req2Test evaluation")
    parser.add_argument("--dataset", required=True, help="Golden Dataset JSONL path")
    parser.add_argument("--mode", choices=("demo", "openai_compatible"), default="demo")
    parser.add_argument("--min-score", type=float, default=80.0)
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--base-url", default="https://api.openai.com/v1")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--prompt-version",
        choices=("workflow-v1", "workflow-grounded-v2"),
        default="workflow-v1",
    )
    parser.add_argument("--output", help="Optional path for the complete JSON report")
    return parser


def run_evaluation_command(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 0 <= args.min_score <= 100:
        raise SystemExit("--min-score must be between 0 and 100")

    try:
        dataset = load_golden_dataset(args.dataset)
        api_key = ""
        if args.mode == "openai_compatible":
            api_key = os.getenv("REQ2TEST_EVAL_API_KEY", os.getenv("OPENAI_API_KEY", ""))
        settings = LLMSettings(
            mode=args.mode,
            model=args.model,
            api_key=api_key,
            base_url=args.base_url,
            temperature=args.temperature,
            seed=args.seed,
        )
        generation = GenerationConfig(prompt_version=args.prompt_version, max_cases=30)
        report = evaluate_golden_dataset(
            dataset,
            llm_settings=settings,
            generation_config=generation,
            judge_settings=settings,
        )
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:  # noqa: BLE001 - CLI failures must produce a nonzero gate
        print(
            json.dumps(
                {"status": "error", "error": safe_failure_reason(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    passed = report.status == "completed" and report.overall_score >= args.min_score
    summary = {
        "status": "passed" if passed else "failed",
        "run_status": report.status,
        "mode": args.mode,
        "dataset": report.dataset_name,
        "dataset_version": report.dataset_version,
        "dataset_digest": report.dataset_digest,
        "prompt_version": report.configuration.prompt_version,
        "prompt_digest": report.configuration.prompt_digest,
        "model": report.configuration.model,
        "temperature": report.configuration.temperature,
        "seed": report.configuration.seed,
        "overall_score": report.overall_score,
        "min_score": args.min_score,
        "metric_scores": report.metric_scores,
        "case_count": len(report.cases),
        "failure_reason": report.failure_reason,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


def main() -> None:
    raise SystemExit(run_evaluation_command())


if __name__ == "__main__":
    main()
