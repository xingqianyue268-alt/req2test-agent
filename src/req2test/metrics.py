"""Deterministic quality metrics for generated test suites."""

from __future__ import annotations

from .models import WorkflowResult


def structural_completeness(result: WorkflowResult) -> float:
    if not result.test_cases:
        return 0.0
    scores: list[float] = []
    for case in result.test_cases:
        checks = [
            bool(case.title.strip()),
            bool(case.module.strip()),
            bool(case.preconditions),
            len(case.steps) >= 2,
            all(step.action.strip() and step.expected.strip() for step in case.steps),
            bool(case.source_requirement.strip()),
        ]
        scores.append(sum(checks) / len(checks))
    return round(sum(scores) / len(scores), 4)


def duplicate_title_rate(result: WorkflowResult) -> float:
    titles = [case.title.strip() for case in result.test_cases if case.title.strip()]
    if not titles:
        return 0.0
    duplicate_count = len(titles) - len(set(titles))
    return round(duplicate_count / len(titles), 4)


def average_step_count(result: WorkflowResult) -> float:
    if not result.test_cases:
        return 0.0
    return round(sum(len(case.steps) for case in result.test_cases) / len(result.test_cases), 2)
