"""Strict, versioned contracts shared by every evaluation entry point."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EvaluationMetricName = Literal[
    "requirement_coverage",
    "case_completeness",
    "executability",
    "expected_result_quality",
    "requirement_groundedness",
    "redundancy",
]

EVALUATION_METRIC_NAMES: tuple[EvaluationMetricName, ...] = (
    "requirement_coverage",
    "case_completeness",
    "executability",
    "expected_result_quality",
    "requirement_groundedness",
    "redundancy",
)


class StrictEvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoldenExpectation(StrictEvaluationModel):
    """One stable, human-auditable expectation in a golden record."""

    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2000)
    keywords: list[str] = Field(min_length=1, max_length=20)

    @field_validator("id", "text")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if not normalized:
            raise ValueError("keywords must contain at least one non-blank value")
        if len(normalized) != len(set(normalized)):
            raise ValueError("keywords must not contain duplicates")
        return normalized


class GoldenDatasetCase(StrictEvaluationModel):
    """One public, versioned evaluation scenario."""

    id: str = Field(min_length=1, max_length=128)
    requirement_text: str = Field(min_length=1, max_length=100_000)
    expected_requirements: list[GoldenExpectation] = Field(min_length=1, max_length=100)
    expected_constraints: list[GoldenExpectation] = Field(default_factory=list, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=30)
    dataset_version: str = Field(min_length=1, max_length=128)

    @field_validator("id", "requirement_text", "dataset_version")
    @classmethod
    def strip_case_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().lower() for value in values if value.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("tags must not contain duplicates")
        return normalized


class GoldenDataset(StrictEvaluationModel):
    """Validated dataset snapshot identified by both version and content digest."""

    path: Path
    name: str
    dataset_version: str
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: list[GoldenDatasetCase] = Field(min_length=1)


class EvaluationMetricResult(StrictEvaluationModel):
    """Normalized result contract used by deterministic and Judge evaluators."""

    metric: EvaluationMetricName
    score: float = Field(ge=0.0, le=100.0)
    reason: str = Field(min_length=1, max_length=4000)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    evaluator: Literal["deterministic", "llm_judge", "deterministic_fallback"]
    evaluator_version: str = Field(min_length=1, max_length=128)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason must not be blank")
        return value


class JudgeMetadata(StrictEvaluationModel):
    """Non-secret metadata describing one subjective evaluation attempt."""

    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=255)
    temperature: float = Field(ge=0.0, le=1.0)
    prompt_version: str = Field(min_length=1, max_length=128)
    prompt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    fallback_used: bool = False
    fallback_reason: str | None = Field(default=None, max_length=500)


class JudgeOutcome(StrictEvaluationModel):
    metrics: dict[EvaluationMetricName, EvaluationMetricResult]
    metadata: JudgeMetadata


class EvaluationConfigurationMetadata(StrictEvaluationModel):
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=255)
    temperature: float = Field(ge=0.0, le=1.0)
    seed: int | None = None
    prompt_version: str = Field(min_length=1, max_length=128)
    prompt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_config: dict[str, Any]
    knowledge_base_identifier: str = Field(min_length=1, max_length=255)
    knowledge_base_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    aggregation_version: str = Field(min_length=1, max_length=128)


class EvaluationCaseReport(StrictEvaluationModel):
    dataset_case_id: str
    metrics: dict[EvaluationMetricName, EvaluationMetricResult]
    overall_score: float = Field(ge=0.0, le=100.0)
    latency_ms: float = Field(ge=0.0)
    revision_iterations: int = Field(default=0, ge=0)
    failure_reason: str | None = Field(default=None, max_length=1000)
    judge_metadata: JudgeMetadata
    generated_result: dict[str, Any] | None = None


class EvaluationRunReport(StrictEvaluationModel):
    dataset_name: str
    dataset_version: str
    dataset_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["completed", "failed"]
    configuration: EvaluationConfigurationMetadata
    started_at: datetime
    ended_at: datetime
    latency_ms: float = Field(ge=0.0)
    metric_scores: dict[EvaluationMetricName, float]
    overall_score: float = Field(ge=0.0, le=100.0)
    revision_iterations: int = Field(default=0, ge=0)
    failure_reason: str | None = Field(default=None, max_length=1000)
    cases: list[EvaluationCaseReport]


class MetricComparison(StrictEvaluationModel):
    configuration_a: float
    configuration_b: float
    delta: float


class EvaluationComparisonReport(StrictEvaluationModel):
    dataset_version: str
    dataset_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    metrics: dict[EvaluationMetricName, MetricComparison]
    overall: MetricComparison
    latency_ms: MetricComparison
    revision_iterations: MetricComparison
