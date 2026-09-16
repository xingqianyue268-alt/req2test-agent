"""Docker startup: opt-in migrations, disposable knowledge index, one web process."""

import logging
import os
import sys
import tempfile

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from alembic import command

from .settings import get_settings, normalize_database_url, single_service_mode

def migrate() -> None:
    """Serialize deploys on a direct connection; never stamp, reset or downgrade."""
    url = normalize_database_url(
        os.getenv("DATABASE_URL_UNPOOLED") or get_settings().database_url
    )
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT pg_advisory_lock(7265733274657374)"))
            connection.commit()
            try:
                config = Config("alembic.ini")
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                connection.commit()
            finally:
                connection.rollback()
                connection.execute(text("SELECT pg_advisory_unlock(7265733274657374)"))
                connection.commit()
    finally:
        engine.dispose()


def prepare_knowledge() -> None:
    from .db.session import session_scope
    from .services.knowledge_service import KnowledgeService

    try:
        with session_scope() as session:
            # Seed detects a missing index and restores all uploaded source text
            # from PostgreSQL as well as the built-in catalog.
            KnowledgeService().seed(session)
    except Exception as exc:
        # A vector backend failure must not prevent login or database access.
        # Avoid logging connection strings or credentials from external errors.
        logging.warning("Knowledge index initialization deferred (%s)", type(exc).__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    single_service_mode()  # Fail fast on an unsafe memory/worker combination.
    get_settings()  # Validate production secrets before database changes.
    if os.getenv("REQ2TEST_CHROMA_EPHEMERAL", "false").lower() in {"true", "1", "yes"}:
        # Fresh namespace avoids corrupt/stale local indexes across restarts.
        root = os.getenv("REQ2TEST_CHROMA_DIR", "/tmp/req2test-chroma")
        os.makedirs(root, exist_ok=True)
        os.environ["REQ2TEST_CHROMA_DIR"] = tempfile.mkdtemp(prefix="boot-", dir=root)
    if os.getenv("REQ2TEST_AUTO_MIGRATE", "false").lower() in {"true", "1", "yes"}:
        migrate()
        prepare_knowledge()
    os.execv(sys.executable, [
        sys.executable, "-m", "uvicorn", "req2test.api:app",
        "--host", "0.0.0.0", "--port", os.getenv("PORT", "8000"), "--workers", "1",
    ])


if __name__ == "__main__":
    main()
