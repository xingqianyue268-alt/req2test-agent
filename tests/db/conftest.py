from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from req2test.settings import get_settings


@pytest.fixture(scope="session")
def postgres_engine() -> Iterator[Engine]:
    url = os.getenv("REQ2TEST_TEST_DATABASE_URL", get_settings().database_url)
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"real PostgreSQL is required for database integration tests: {exc}")
    yield engine
    engine.dispose()


def _alembic_config(connection: Connection) -> Config:
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    return config


@pytest.fixture(scope="session")
def migrated_schema(postgres_engine: Engine) -> Iterator[str]:
    schema = f"req2test_test_{uuid.uuid4().hex}"
    with postgres_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    with postgres_engine.connect() as connection:
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()
        command.upgrade(_alembic_config(connection), "head")
        connection.commit()

    yield schema

    with postgres_engine.begin() as connection:
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


@pytest.fixture()
def schema_connection(postgres_engine: Engine, migrated_schema: str) -> Iterator[Connection]:
    with postgres_engine.connect() as connection:
        connection.execute(text(f'SET search_path TO "{migrated_schema}"'))
        connection.commit()
        yield connection


@pytest.fixture()
def db_session(schema_connection: Connection) -> Iterator[Session]:
    transaction = schema_connection.begin()
    session = Session(bind=schema_connection, autoflush=False, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
