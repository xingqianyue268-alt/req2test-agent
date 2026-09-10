"""Application service for safe dataset lookup and evaluation dispatch."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import GenerationConfig, LLMSettings
from ..db.models import EvaluationComparisonORM, EvaluationRunORM, KnowledgeDocumentORM
from ..db.repositories import evaluations
from ..db.services.evaluation_persistence import EvaluationPersistenceService
from ..evaluation.dataset import DatasetLoadError, discover_golden_datasets, load_golden_dataset
from ..evaluation.engine import default_knowledge_snapshot
from ..evaluation.models import GoldenDataset
from ..evaluation.safety import safe_failure_reason

Publisher = Callable[[list[Any], bool], str]
_SAFE_DATASET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class EvaluationDispatchError(RuntimeError):
    pass


class EvaluationDatasetRegistry:
    def __init__(self, root: str | Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[3]
        configured = root or os.getenv("REQ2TEST_EVAL_DATASET_DIR", project_root / "evals")
        self.root = Path(configured).expanduser().resolve()

    def list(self) -> list[GoldenDataset]:
        return discover_golden_datasets(self.root)

    def get(self, name: str) -> GoldenDataset:
        if not _SAFE_DATASET_NAME.fullmatch(name) or Path(name).name != name:
            raise DatasetLoadError("Invalid evaluation dataset name")
        path = (self.root / f"{name}.jsonl").resolve()
        if path.parent != self.root:
            raise DatasetLoadError("Evaluation dataset must remain inside the dataset directory")
        return load_golden_dataset(path)


def current_knowledge_snapshot(session: Session) -> tuple[str, str]:
    base_identifier, base_digest = default_knowledge_snapshot()
    records = list(
        session.scalars(
            select(KnowledgeDocumentORM).order_by(
                KnowledgeDocumentORM.vector_collection,
                KnowledgeDocumentORM.vector_document_id,
            )
        )
    )
    digest = hashlib.sha256(base_digest.encode("ascii"))
    collections: set[str] = set()
    for record in records:
        collections.add(record.vector_collection)
        fields = (
            record.vector_collection,
            record.vector_document_id,
            hashlib.sha256(record.content_text.encode("utf-8")).hexdigest(),
            str(record.chunk_count),
            record.index_status,
        )
        digest.update("\0".join(fields).encode("utf-8"))
        digest.update(b"\0")
    collection_label = "+".join(sorted(collections)) if collections else "repository"
    return (
        f"{base_identifier}|catalog={collection_label}|documents={len(records)}",
        digest.hexdigest(),
    )


def dataset_dto(dataset: GoldenDataset) -> dict[str, Any]:
    tags = sorted({tag for case in dataset.cases for tag in case.tags})
    return {
        "name": dataset.name,
        "dataset_version": dataset.dataset_version,
        "digest": dataset.digest,
        "case_count": len(dataset.cases),
        "tags": tags,
    }


def run_dto(run: EvaluationRunORM, *, include_cases: bool = False) -> dict[str, Any]:
    payload = {
        "id": str(run.id),
        "user_id": str(run.user_id) if run.user_id else None,
        "status": run.status,
        "configuration_label": run.configuration_label,
        "dataset_name": run.dataset_name,
        "dataset_version": run.dataset_version,
        "dataset_digest": run.dataset_digest,
        "provider": run.provider,
        "model": run.model,
        "temperature": float(run.temperature),
        "seed": run.seed,
        "prompt_version": run.prompt_version,
        "prompt_digest": run.prompt_digest,
        "generation_config": run.generation_config,
        "judge_config": run.judge_config,
        "knowledge_base_identifier": run.knowledge_base_identifier,
        "knowledge_base_digest": run.knowledge_base_digest,
        "aggregation_version": run.aggregation_version,
        "metric_scores": run.metric_scores,
        "overall_score": float(run.overall_score) if run.overall_score is not None else None,
        "revision_iterations": run.revision_iterations,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "latency_ms": float(run.latency_ms) if run.latency_ms is not None else None,
        "failure_reason": run.failure_reason,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
    if include_cases:
        payload["cases"] = [
            {
                "id": str(case.id),
                "dataset_case_id": case.dataset_case_id,
                "metric_scores": case.metric_scores,
                "overall_score": float(case.overall_score),
                "latency_ms": float(case.latency_ms),
                "revision_iterations": case.revision_iterations,
                "failure_reason": case.failure_reason,
                "judge_metadata": case.judge_metadata,
                "generated_result": case.generated_result,
            }
            for case in sorted(run.case_results, key=lambda item: item.dataset_case_id)
        ]
    return payload


def comparison_dto(comparison: EvaluationComparisonORM) -> dict[str, Any]:
    return {
        "id": str(comparison.id),
        "user_id": str(comparison.user_id) if comparison.user_id else None,
        "name": comparison.name,
        "status": comparison.status,
        "dataset_version": comparison.dataset_version,
        "dataset_digest": comparison.dataset_digest,
        "run_a_id": str(comparison.run_a_id),
        "run_b_id": str(comparison.run_b_id),
        "summary": comparison.summary,
        "failure_reason": comparison.failure_reason,
        "completed_at": comparison.completed_at.isoformat() if comparison.completed_at else None,
        "created_at": comparison.created_at.isoformat() if comparison.created_at else None,
    }


class EvaluationService:
    def __init__(
        self,
        publisher: Publisher,
        registry: EvaluationDatasetRegistry | None = None,
        persistence: EvaluationPersistenceService | None = None,
    ) -> None:
        self.publisher = publisher
        self.registry = registry or EvaluationDatasetRegistry()
        self.persistence = persistence or EvaluationPersistenceService()

    def create_and_dispatch(
        self,
        session: Session,
        *,
        dataset_name: str,
        user_id: uuid.UUID,
        llm_settings: LLMSettings,
        generation_config: GenerationConfig,
        judge_settings: LLMSettings | None = None,
        configuration_label: str = "single",
        eager: bool = False,
    ) -> EvaluationRunORM:
        dataset = self.registry.get(dataset_name)
        kb_identifier, kb_digest = current_knowledge_snapshot(session)
        run = self.persistence.create_run(
            session,
            dataset=dataset,
            user_id=user_id,
            llm_settings=llm_settings,
            generation_config=generation_config,
            judge_settings=judge_settings,
            knowledge_base_identifier=kb_identifier,
            knowledge_base_digest=kb_digest,
            configuration_label=configuration_label,
        )
        session.commit()
        session.refresh(run)
        args = [
            str(run.id),
            dataset.name,
            dataset.digest,
            llm_settings.model_dump(),
            generation_config.model_dump(),
            (judge_settings or llm_settings).model_dump(),
            kb_identifier,
            kb_digest,
        ]
        try:
            self.publisher(args, eager)
        except Exception as exc:
            evaluations.mark_evaluation_run_failed(
                session, run.id, f"Dispatch failed: {safe_failure_reason(exc)}"
            )
            session.commit()
            raise EvaluationDispatchError("Evaluation dispatch failed") from exc
        return run

    def create_comparison_and_dispatch(
        self,
        session: Session,
        *,
        name: str,
        dataset_name: str,
        user_id: uuid.UUID,
        configuration_a: tuple[LLMSettings, GenerationConfig, LLMSettings | None],
        configuration_b: tuple[LLMSettings, GenerationConfig, LLMSettings | None],
        eager: bool = False,
    ) -> EvaluationComparisonORM:
        dataset = self.registry.get(dataset_name)
        kb_identifier, kb_digest = current_knowledge_snapshot(session)
        run_ids = (uuid.uuid4(), uuid.uuid4())
        runs: list[EvaluationRunORM] = []
        for label, run_id, configuration in zip(("A", "B"), run_ids, (configuration_a, configuration_b)):
            llm, generation, judge = configuration
            runs.append(
                self.persistence.create_run(
                    session,
                    dataset=dataset,
                    user_id=user_id,
                    llm_settings=llm,
                    generation_config=generation,
                    judge_settings=judge,
                    run_id=run_id,
                    knowledge_base_identifier=kb_identifier,
                    knowledge_base_digest=kb_digest,
                    configuration_label=label,
                )
            )
        comparison = self.persistence.create_comparison(
            session,
            name=name,
            user_id=user_id,
            dataset=dataset,
            run_a_id=runs[0].id,
            run_b_id=runs[1].id,
        )
        session.commit()
        session.refresh(comparison)
        try:
            for run, configuration in zip(runs, (configuration_a, configuration_b)):
                llm, generation, judge = configuration
                self.publisher(
                    [
                        str(run.id),
                        dataset.name,
                        dataset.digest,
                        llm.model_dump(),
                        generation.model_dump(),
                        (judge or llm).model_dump(),
                        kb_identifier,
                        kb_digest,
                    ],
                    eager,
                )
        except Exception as exc:
            for run in runs:
                evaluations.mark_evaluation_run_failed(
                    session,
                    run.id,
                    f"Comparison dispatch failed: {safe_failure_reason(exc)}",
                )
            self.persistence.refresh_comparisons_for_run(session, runs[0].id)
            session.commit()
            raise EvaluationDispatchError("A/B evaluation dispatch failed") from exc
        session.refresh(comparison)
        if comparison.status == "queued":
            comparison.status = "running"
            session.commit()
        session.refresh(comparison)
        return comparison
