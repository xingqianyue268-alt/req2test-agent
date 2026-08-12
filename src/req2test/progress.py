"""Progress-aware execution helpers for the Req2Test LangGraph workflow."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .config import GenerationConfig, LLMSettings
from .graph import build_graph
from .models import ReviewReport, RequirementItem, TestCase, WorkflowResult

ProgressCallback = Callable[[str, int, str], None]

# Keep headroom after generation so the async worker can continue with the
# Tool Calling / HTTP / Pytest execution stage before marking the task complete.
_STAGE_PROGRESS = {
    "retrieve_context": ("retrieval", 12, "正在检索测试规则和历史测试用例"),
    "analyse_requirements": ("analysis", 28, "正在拆分并分析需求"),
    "design_cases": ("design", 52, "正在生成测试用例"),
    "review_cases": ("review", 68, "正在执行质量评审"),
    "revise_cases": ("revision", 76, "评审未通过，正在修订用例"),
}


def _to_result(state: dict[str, Any]) -> WorkflowResult:
    requirements = [RequirementItem.model_validate(item) for item in state.get("requirements", [])]
    cases = [TestCase.model_validate(item) for item in state.get("test_cases", [])]
    review = ReviewReport.model_validate(
        state.get(
            "review",
            {"score": 0, "coverage_rate": 0.0, "issues": ["未生成评审结果"], "suggestions": []},
        )
    )
    return WorkflowResult(
        requirements=requirements,
        test_cases=cases,
        review=review,
        retrieved_context=state.get("retrieved_context", []),
        errors=state.get("errors", []),
    )


def run_workflow_with_progress(
    requirement_text: str,
    llm_settings: LLMSettings | None = None,
    generation_config: GenerationConfig | None = None,
    on_progress: ProgressCallback | None = None,
) -> WorkflowResult:
    requirement_text = requirement_text.strip()
    if not requirement_text:
        raise ValueError("需求文本不能为空")

    settings = llm_settings or LLMSettings()
    config = generation_config or GenerationConfig()
    initial_state: dict[str, Any] = {
        "requirement_text": requirement_text,
        "llm_settings": settings.model_dump(),
        "generation_config": config.model_dump(),
        "review_iterations": 0,
        "errors": [],
    }

    graph = build_graph()
    latest_state = dict(initial_state)

    if on_progress:
        on_progress("started", 5, "任务开始执行")

    if hasattr(graph, "stream"):
        for update in graph.stream(initial_state, stream_mode="updates"):
            for node_name, node_update in update.items():
                if isinstance(node_update, dict):
                    latest_state.update(node_update)
                if on_progress and node_name in _STAGE_PROGRESS:
                    stage, progress, message = _STAGE_PROGRESS[node_name]
                    on_progress(stage, progress, message)
    else:
        latest_state = graph.invoke(initial_state)

    if on_progress:
        on_progress("generation_completed", 80, "测试用例生成与质量评审已完成")
    return _to_result(latest_state)
