"""LangGraph workflow assembly and public execution function."""

from __future__ import annotations

from typing import Any

from .config import GenerationConfig, LLMSettings
from .models import ReviewReport, RequirementItem, TestCase, WorkflowResult
from .nodes import (
    WorkflowState,
    analyse_requirements_node,
    design_cases_node,
    retrieve_context_node,
    review_cases_node,
    revise_cases_node,
    route_after_review,
)

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - only used in restricted offline environments
    END = START = StateGraph = None


class _OfflineGraph:
    """Small fallback runner used only when LangGraph is unavailable.

    The normal installed project always uses LangGraph. This fallback keeps the
    demo workflow and unit tests executable in restricted environments where
    dependencies cannot be downloaded.
    """

    def invoke(self, initial_state: WorkflowState) -> WorkflowState:
        state: WorkflowState = dict(initial_state)
        for node in (
            retrieve_context_node,
            analyse_requirements_node,
            design_cases_node,
            review_cases_node,
        ):
            state.update(node(state))

        while route_after_review(state) == "revise":
            state.update(revise_cases_node(state))
            state.update(review_cases_node(state))
        return state


def build_graph():
    if StateGraph is None:
        return _OfflineGraph()

    builder = StateGraph(WorkflowState)
    builder.add_node("retrieve_context", retrieve_context_node)
    builder.add_node("analyse_requirements", analyse_requirements_node)
    builder.add_node("design_cases", design_cases_node)
    builder.add_node("review_cases", review_cases_node)
    builder.add_node("revise_cases", revise_cases_node)

    builder.add_edge(START, "retrieve_context")
    builder.add_edge("retrieve_context", "analyse_requirements")
    builder.add_edge("analyse_requirements", "design_cases")
    builder.add_edge("design_cases", "review_cases")
    builder.add_conditional_edges(
        "review_cases",
        route_after_review,
        {"revise": "revise_cases", "finish": END},
    )
    builder.add_edge("revise_cases", "review_cases")
    return builder.compile()


def run_workflow(
    requirement_text: str,
    llm_settings: LLMSettings | None = None,
    generation_config: GenerationConfig | None = None,
) -> WorkflowResult:
    requirement_text = requirement_text.strip()
    if not requirement_text:
        raise ValueError("需求文本不能为空")

    settings = llm_settings or LLMSettings()
    config = generation_config or GenerationConfig()
    graph = build_graph()
    state: dict[str, Any] = graph.invoke(
        {
            "requirement_text": requirement_text,
            "llm_settings": settings.model_dump(),
            "generation_config": config.model_dump(),
            "review_iterations": 0,
            "errors": [],
        }
    )

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
