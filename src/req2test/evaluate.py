"""Run a small reproducible benchmark in offline demo mode."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from statistics import mean
from typing import Any

from .config import GenerationConfig, LLMSettings
from .graph import run_workflow
from .metrics import average_step_count, duplicate_title_rate, structural_completeness


def evaluate_dataset(dataset_path: str | Path) -> dict[str, Any]:
    records = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []

    for record in records:
        started = time.perf_counter()
        result = run_workflow(
            record["text"],
            LLMSettings(mode="demo"),
            GenerationConfig(
                include_positive=True,
                include_negative=True,
                include_edge=False,
                max_cases=30,
            ),
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        actual_modules = {item.module for item in result.requirements}
        expected_modules = set(record.get("expected_modules", []))
        module_recall = (
            len(actual_modules & expected_modules) / len(expected_modules)
            if expected_modules
            else 1.0
        )
        results.append(
            {
                "id": record["id"],
                "requirement_count": len(result.requirements),
                "meets_min_requirement_count": len(result.requirements)
                >= int(record.get("min_requirements", 0)),
                "module_recall": round(module_recall, 4),
                "traceability_coverage": result.review.coverage_rate,
                "structural_completeness": structural_completeness(result),
                "duplicate_title_rate": duplicate_title_rate(result),
                "average_step_count": average_step_count(result),
                "elapsed_ms": elapsed_ms,
            }
        )

    return {
        "mode": "demo",
        "dataset_size": len(results),
        "aggregate": {
            "min_requirement_count_pass_rate": round(
                mean(1.0 if item["meets_min_requirement_count"] else 0.0 for item in results), 4
            ),
            "average_module_recall": round(mean(item["module_recall"] for item in results), 4),
            "average_traceability_coverage": round(
                mean(item["traceability_coverage"] for item in results), 4
            ),
            "average_structural_completeness": round(
                mean(item["structural_completeness"] for item in results), 4
            ),
            "average_duplicate_title_rate": round(
                mean(item["duplicate_title_rate"] for item in results), 4
            ),
            "average_elapsed_ms": round(mean(item["elapsed_ms"] for item in results), 2),
        },
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="评估 Req2Test Agent 演示工作流")
    parser.add_argument("--dataset", default="evaluation/dataset.json")
    parser.add_argument("--output", default="output/evaluation_report.json")
    args = parser.parse_args()

    report = evaluate_dataset(args.dataset)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))
    print(f"评估报告：{output_path.resolve()}")


if __name__ == "__main__":
    main()
