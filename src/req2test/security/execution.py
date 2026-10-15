"""One target authorization policy for both execution tools."""

from __future__ import annotations

import os
from urllib.parse import urlsplit


def validate_execution_target(base_url: str) -> str:
    """Authorize the base URL before planning, rendering or opening a connection."""
    base_url = base_url.strip()
    if any(ord(char) < 32 for char in base_url) or "\\" in base_url:
        raise ValueError("base_url 不允许控制字符或反斜杠")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base_url 必须是有效的 http:// 或 https:// 地址")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("base_url 不允许携带用户名或密码")
    # A base query/fragment would change the meaning of the appended spec path.
    if parsed.query or parsed.fragment:
        raise ValueError("base_url 不允许携带查询参数或片段")
    _ = parsed.port  # Also reject malformed/out-of-range ports before dispatch.
    allow_remote = os.getenv("REQ2TEST_ALLOW_REMOTE_EXECUTION", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    configured = os.getenv("REQ2TEST_EXECUTION_ALLOWED_HOSTS", "localhost,127.0.0.1,::1,api")
    allowed_hosts = {item.strip().lower() for item in configured.split(",") if item.strip()}
    if not allow_remote and parsed.hostname.lower() not in allowed_hosts:
        raise ValueError("目标主机不在执行白名单中；请由管理员配置允许的测试目标。")
    return base_url.rstrip("/")
