from req2test.config import GenerationConfig, LLMSettings
from req2test.progress import run_workflow_with_progress
import pytest

from req2test.task_store import TaskStore, TaskStoreUnavailable


def test_task_store_falls_back_to_memory():
    store = TaskStore(redis_url="redis://127.0.0.1:1/0")
    state = store.create("task-1")
    assert state["status"] == "queued"
    updated = store.update("task-1", status="running", progress=35)
    assert updated["status"] == "running"
    assert store.get("task-1")["progress"] == 35


def test_task_store_disables_memory_fallback_for_production():
    store = TaskStore(redis_url="redis://127.0.0.1:1/0", allow_memory_fallback=False)
    assert store.backend == "unavailable"
    assert store.can_accept_new_tasks is False
    with pytest.raises(TaskStoreUnavailable):
        store.create("production-task")


def test_demo_workflow_emits_generation_progress_with_execution_headroom():
    events = []
    result = run_workflow_with_progress(
        "用户可以新增供应商并保存，保存后供应商显示在列表中。",
        llm_settings=LLMSettings(mode="demo"),
        generation_config=GenerationConfig(max_cases=4),
        on_progress=lambda stage, progress, message: events.append((stage, progress, message)),
    )
    assert result.requirements
    assert result.test_cases
    assert events[0][0] == "started"
    assert events[-1][0] == "generation_completed"
    assert events[-1][1] == 80
