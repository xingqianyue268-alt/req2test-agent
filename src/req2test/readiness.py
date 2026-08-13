"""Infrastructure readiness probes kept separate from application liveness."""

from __future__ import annotations

import os

from kombu import Connection

from .task_store import TaskStore


def redis_is_ready(store: TaskStore) -> bool:
    return store.ping()


def rabbitmq_is_ready() -> bool:
    broker_url = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
    try:
        with Connection(broker_url, connect_timeout=1) as connection:
            connection.ensure_connection(max_retries=0)
    except Exception:  # Kombu transport errors vary by broker and network stack.
        return False
    return True
