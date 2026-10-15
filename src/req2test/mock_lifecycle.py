"""Only the opt-in disposable loopback fixture supports automatic preparation/cleanup."""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlsplit

import httpx

from .security.execution import validate_execution_target


class MockLifecycleError(ValueError):
    pass


def validate_mock_target(base_url: str) -> str:
    target = validate_execution_target(base_url)
    parsed = urlsplit(target)
    if (
        os.getenv("REQ2TEST_ENV") != "test"
        or os.getenv("REQ2TEST_ENABLE_MOCK_LIFECYCLE", "false").lower() != "true"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.path not in {"", "/"}
    ):
        raise MockLifecycleError(
            "自动准备/清理仅限管理员启用的 test 模式、纯 loopback 本地 Mock 根地址"
        )
    return target


class MockLifecycle:
    def __init__(self, base_url: str, seed: list[dict]):
        self.target = validate_mock_target(base_url)
        self.run_id = uuid.uuid4().hex
        self.seed = seed
        self.verified = False
        self.state = {"run_id": self.run_id, "setup": "not_started", "cleanup": "not_started"}

    def prepare(self):
        try:
            with httpx.Client(timeout=3, follow_redirects=False, trust_env=False) as client:
                response = client.get(self.target + "/__req2test__/capabilities")
                capability = response.json() if response.status_code == 200 else None
                if (
                    not isinstance(capability, dict)
                    or capability.get("protocol") != "req2test-disposable-v1"
                ):
                    raise MockLifecycleError("目标未声明专用 Mock 隔离协议")
                self.verified = True
                response = client.put(
                    self.target + "/__req2test__/runs/" + self.run_id, json={"products": self.seed}
                )
                if response.status_code != 201:
                    raise MockLifecycleError("Mock 前置数据准备失败")
            self.state["setup"] = "passed"
        except (httpx.HTTPError, ValueError):
            self.state["setup"] = "error"
            self.state["error"] = "本地 Mock 前置数据准备失败，未执行测试用例"
            raise MockLifecycleError(self.state["error"]) from None

    def cleanup(self):
        if not self.verified:
            self.state["cleanup"] = "not_attempted"
            return
        try:
            with httpx.Client(timeout=3, follow_redirects=False, trust_env=False) as client:
                response = client.delete(self.target + "/__req2test__/runs/" + self.run_id)
                if response.status_code not in {204, 404}:
                    raise MockLifecycleError("Mock 清理失败")
            self.state["cleanup"] = "passed"
        except (httpx.HTTPError, ValueError):
            self.state["cleanup"] = "error"
            self.state["error"] = "本地 Mock 清理未确认成功；请检查隔离区，不能视为完整通过"
