"""Redis live task projection with an explicitly local-only memory fallback."""

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
    """Store live task state without silently masking production Redis failures."""

    def __init__(
        self,
        redis_url: str | None = None,
        *,
        allow_memory_fallback: bool | None = None,
    ) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        environment = os.getenv("REQ2TEST_ENV", "local").strip().lower()
        self.allow_memory_fallback = (
            environment in {"local", "development", "dev", "test"}
            if allow_memory_fallback is None
            else allow_memory_fallback
        )
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
        if self._redis is not None:
            return "redis"
        return "memory" if self.allow_memory_fallback else "unavailable"

    @property
    def can_accept_new_tasks(self) -> bool:
        return self._redis is not None or self.allow_memory_fallback

    def ping(self) -> bool:
        """Check the real Redis dependency; memory fallback is not Redis readiness."""

        if self._redis is None:
            return False
        try:
            return bool(self._redis.ping())
        except Exception:  # noqa: BLE001
            return False

    def _require_backend(self) -> None:
        if self._redis is None and not self.allow_memory_fallback:
            raise TaskStoreUnavailable("Redis is unavailable and memory fallback is disabled")

    def _key(self, task_id: str) -> str:
        return f"req2test:task:{task_id}"

    def create(self, task_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._require_backend()
        state = {
            "task_id": task_id,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "state_version": 1,
            "celery_task_id": None,
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
        self._require_backend()
        state = {**state, "updated_at": _utc_now()}
        if self._redis is not None:
            try:
                self._redis.set(
                    self._key(task_id), json.dumps(state, ensure_ascii=False), ex=86400
                )
                return
            except Exception as exc:  # noqa: BLE001
                if not self.allow_memory_fallback:
                    raise TaskStoreUnavailable("Redis write failed") from exc
                self._redis = None
        with self._lock:
            self._memory[task_id] = state

    def get(self, task_id: str) -> dict[str, Any] | None:
        self._require_backend()
        if self._redis is not None:
            try:
                raw = self._redis.get(self._key(task_id))
                return json.loads(raw) if raw else None
            except Exception as exc:  # noqa: BLE001
                if not self.allow_memory_fallback:
                    raise TaskStoreUnavailable("Redis read failed") from exc
                self._redis = None
        with self._lock:
            state = self._memory.get(task_id)
            return dict(state) if state else None

    def update(self, task_id: str, **changes: Any) -> dict[str, Any]:
        state = self.get(task_id) or {"task_id": task_id, "created_at": _utc_now()}
        state.update(changes)
        self.set(task_id, state)
        return state


class TaskStoreUnavailable(RuntimeError):
    """Raised when production requires Redis but it cannot serve projections."""


task_store = TaskStore()
