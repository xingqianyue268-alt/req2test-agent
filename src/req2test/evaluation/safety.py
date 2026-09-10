"""Small redaction helpers for persisted evaluation failures."""

from __future__ import annotations

import re


def safe_failure_reason(error: BaseException | str, *, max_length: int = 500) -> str:
    """Return a single-line error summary with common credential forms removed."""

    value = str(error).replace("\n", " ").strip()
    if not value:
        value = error.__class__.__name__ if isinstance(error, BaseException) else "Unknown error"
    value = re.sub(
        r"(?i)(api[_-]?key|authorization|cookie|password|secret|token)\s*[=:]\s*[^\s,;]+",
        r"\1=***",
        value,
    )
    value = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer ***", value)
    return value[:max_length]
