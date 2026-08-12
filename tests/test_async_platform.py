from req2test.config import GenerationConfig, LLMSettings
from req2test.progress import run_workflow_with_progress
from req2test.task_store import TaskStore


def test_task_store_falls_back_to_memory():
    store = TaskStore(redis_url="redis://127.0.0.1:1/0")
    state = store.create("task-1")
    assert state["status"] == "queued"
    updated = store.update("task-1", status="running", progress=35)
    assert updated["status"] == "running"
    assert store.get("task-1")["progress"] == 35


def test_demo_workflow_emits_progress():
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
    assert events[-1][0] == "completed"
    assert events[-1][1] == 100
