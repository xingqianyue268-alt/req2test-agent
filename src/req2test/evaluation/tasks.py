"""Celery task for durable Evaluation Center runs."""

from __future__ import annotations

import logging
import uuid

from ..config import GenerationConfig, LLMSettings
from ..db.repositories import evaluations
from ..db.services.evaluation_persistence import EvaluationPersistenceService
from ..db.session import session_scope
from ..services.evaluation_service import EvaluationDatasetRegistry, current_knowledge_snapshot
from ..worker import celery_app
from .engine import evaluate_golden_dataset
from .safety import safe_failure_reason

logger = logging.getLogger(__name__)


@celery_app.task(name="req2test.evaluate")
def run_evaluation(
    run_id: str,
    dataset_name: str,
    expected_dataset_digest: str,
    llm_settings: dict,
    generation_config: dict,
    judge_settings: dict,
    knowledge_base_identifier: str,
    knowledge_base_digest: str,
) -> dict:
    """Evaluate one immutable input snapshot and persist every result."""

    parsed_run_id = uuid.UUID(run_id)
    persistence = EvaluationPersistenceService()
    try:
        dataset = EvaluationDatasetRegistry().get(dataset_name)
        if dataset.digest != expected_dataset_digest:
            raise ValueError("Golden dataset digest changed after this run was queued")

        with session_scope() as session:
            run = evaluations.mark_evaluation_run_running(session, parsed_run_id)
            if run.status in {"completed", "failed"}:
                return {"run_id": run_id, "status": run.status}
            actual_identifier, actual_digest = current_knowledge_snapshot(session)
            if (actual_identifier, actual_digest) != (
                knowledge_base_identifier,
                knowledge_base_digest,
            ):
                raise ValueError("Knowledge base snapshot changed after this run was queued")

        report = evaluate_golden_dataset(
            dataset,
            llm_settings=LLMSettings.model_validate(llm_settings),
            generation_config=GenerationConfig.model_validate(generation_config),
            judge_settings=LLMSettings.model_validate(judge_settings),
            knowledge_base_identifier=knowledge_base_identifier,
            knowledge_base_digest=knowledge_base_digest,
        )
        with session_scope() as session:
            persistence.persist_report(session, parsed_run_id, report)
            persistence.refresh_comparisons_for_run(session, parsed_run_id)
        return {
            "run_id": run_id,
            "status": report.status,
            "overall_score": report.overall_score,
        }
    except Exception as exc:
        reason = safe_failure_reason(exc, max_length=1000)
        try:
            with session_scope() as session:
                evaluations.mark_evaluation_run_failed(session, parsed_run_id, reason)
                persistence.refresh_comparisons_for_run(session, parsed_run_id)
        except Exception:
            logger.exception("Could not persist failed evaluation run %s", run_id)
        raise
