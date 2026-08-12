"""Task state storage backed by Redis with an in-memory fallback."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStore:
    """Persist task state in Redis when available, otherwise keep it in memory."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._memory: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._redis = None
        if redis is not None:
            try:
                client = redis.Redis.from_url(self.redis_url, decode_responses=True)
                client.ping()
                self._redis = client
            except Exception:  # noqa: BLE001
                self._redis = None

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def _key(self, task_id: str) -> str:
        return f"req2test:task:{task_id}"

    def create(self, task_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        state = {
            "task_id": task_id,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "message": "任务已提交，等待处理",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "result": None,
            "error": None,
            "payload": payload or {},
        }
        self.set(task_id, state)
        return state

    def set(self, task_id: str, state: dict[str, Any]) -> None:
        state = {**state, "updated_at": _utc_now()}
        if self._redis is not None:
            self._redis.set(self._key(task_id), json.dumps(state, ensure_ascii=False), ex=86400)
            return
        with self._lock:
            self._memory[task_id] = state

    def get(self, task_id: str) -> dict[str, Any] | None:
        if self._redis is not None:
            raw = self._redis.get(self._key(task_id))
            return json.loads(raw) if raw else None
        with self._lock:
            state = self._memory.get(task_id)
            return dict(state) if state else None

    def update(self, task_id: str, **changes: Any) -> dict[str, Any]:
        state = self.get(task_id) or {"task_id": task_id, "created_at": _utc_now()}
        state.update(changes)
        self.set(task_id, state)
        return state


task_store = TaskStore()
