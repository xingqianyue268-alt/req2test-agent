"""Small redaction helpers for persisted evaluation failures."""

from __future__ import annotations

from ..security.redaction import redact_text


def safe_failure_reason(error: BaseException | str, *, max_length: int = 500) -> str:
    """Return a single-line error summary with common credential forms removed."""

    value = str(error).replace("\n", " ").strip()
    if not value:
        value = error.__class__.__name__ if isinstance(error, BaseException) else "Unknown error"
    return redact_text(value)[:max_length]
