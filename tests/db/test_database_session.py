from sqlalchemy import text

from req2test.db.session import SessionLocal
from req2test.settings import Settings


def test_settings_support_database_pool_configuration(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://example:test@db:5432/example")
    monkeypatch.setenv("DB_POOL_SIZE", "7")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "3")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "12")

    settings = Settings.from_env()

    assert settings.database_url.endswith("@db:5432/example")
    assert settings.db_pool_size == 7
    assert settings.db_max_overflow == 3
    assert settings.db_pool_timeout == 12


def test_session_factory_uses_required_sync_defaults():
    assert SessionLocal.kw["autoflush"] is False
    assert SessionLocal.kw["expire_on_commit"] is False
    assert SessionLocal.kw["bind"].pool._pre_ping is True


def test_real_postgres_session_executes_query(db_session):
    assert db_session.scalar(text("SELECT 1")) == 1
