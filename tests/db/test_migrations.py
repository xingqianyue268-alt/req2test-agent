from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


EXPECTED_TABLES = {
    "users",
    "tasks",
    "test_cases",
    "executions",
    "knowledge_documents",
}


def _config(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    return config


def test_migration_created_tables_constraints_and_foreign_keys(
    schema_connection, migrated_schema
):
    inspector = inspect(schema_connection)
    assert set(inspector.get_table_names(schema=migrated_schema)) == EXPECTED_TABLES | {
        "alembic_version"
    }

    task_checks = {item["name"] for item in inspector.get_check_constraints("tasks")}
    assert "ck_tasks_progress_range" in task_checks
    user_checks = {item["name"] for item in inspector.get_check_constraints("users")}
    assert "ck_users_role_allowed" in user_checks

    task_indexes = {item["name"]: item for item in inspector.get_indexes("tasks")}
    assert task_indexes["uq_tasks_celery_task_id_not_null"]["unique"] is True

    test_case_unique = {
        item["name"] for item in inspector.get_unique_constraints("test_cases")
    }
    assert "uq_test_cases_task_case_version" in test_case_unique

    execution_unique = {
        item["name"] for item in inspector.get_unique_constraints("executions")
    }
    assert "uq_executions_idempotency_key" in execution_unique

    knowledge_unique = {
        item["name"] for item in inspector.get_unique_constraints("knowledge_documents")
    }
    assert "uq_knowledge_documents_vector_reference" in knowledge_unique
    knowledge_columns = {
        item["name"]: item for item in inspector.get_columns("knowledge_documents")
    }
    assert knowledge_columns["content_text"]["nullable"] is False

    task_fk = inspector.get_foreign_keys("tasks")[0]
    assert task_fk["options"]["ondelete"] == "SET NULL"
    test_case_fk = inspector.get_foreign_keys("test_cases")[0]
    assert test_case_fk["options"]["ondelete"] == "CASCADE"
    execution_fks = {
        tuple(item["constrained_columns"]): item["options"]["ondelete"]
        for item in inspector.get_foreign_keys("executions")
    }
    assert execution_fks[("task_id",)] == "CASCADE"
    assert execution_fks[("test_case_id",)] == "SET NULL"


def test_migration_downgrade_upgrade_round_trip(schema_connection, migrated_schema):
    config = _config(schema_connection)
    schema_connection.commit()
    command.downgrade(config, "base")
    schema_connection.commit()
    assert inspect(schema_connection).get_table_names(schema=migrated_schema) == [
        "alembic_version"
    ]

    command.upgrade(config, "head")
    schema_connection.commit()
    tables = set(inspect(schema_connection).get_table_names(schema=migrated_schema))
    assert tables == EXPECTED_TABLES | {"alembic_version"}
    assert schema_connection.scalar(text("SELECT count(*) FROM alembic_version")) == 1
