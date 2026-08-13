import uuid

from req2test.db.repositories import tasks


def test_task_repository_create_update_and_list(db_session):
    task = tasks.create_task(
        db_session,
        id=uuid.uuid4(),
        title="Repository task",
        requirement_text="A requirement",
        status="queued",
        stage="queued",
        progress=0,
        state_version=1,
        generation_config={},
        execution_config={},
    )
    assert tasks.get_task(db_session, task.id) is task

    updated = tasks.set_celery_task_id(db_session, task.id, "celery-repository")
    assert updated.celery_task_id == "celery-repository"
    assert updated.state_version == 2

    failed = tasks.update_task_state(
        db_session,
        task.id,
        status="failed",
        stage="dispatch_failed",
        error="broker down",
    )
    assert failed.state_version == 3
    assert tasks.list_tasks(db_session, limit=10)[0].id == task.id
