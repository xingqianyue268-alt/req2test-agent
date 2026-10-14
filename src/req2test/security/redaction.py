"""Shared redaction at diagnostic, storage, logging and model-output boundaries.

Execution inputs remain intact. This is field-based redaction, not a general PII
classifier; deployments can add domain-specific fields with REQ2TEST_REDACT_FIELDS.
"""

from __future__ import annotations

import json
import logging
import os
import re
import traceback
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "***"
_SECRET_PARTS = {
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "password",
    "passwd",
    "secret",
    "token",
    "session",
    "apikey",
    "email",
    "phone",
    "mobile",
    "ssn",
}
_KEY_VALUE = re.compile(r"""(?<![\w])(?P<quote>["']?)(?P<key>[\w.-]+)(?P=quote)\s*[:=]\s*""")
_URL = re.compile(r"""[a-zA-Z][a-zA-Z0-9+.-]*://[^\s"'<>]+""")


def is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key))
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    configured = {
        value.strip().lower()
        for value in os.getenv("REQ2TEST_REDACT_FIELDS", "").split(",")
        if value.strip()
    }
    return (
        normalized in configured
        or normalized == "input_value"  # Pydantic exception text echoes rejected inputs.
        or bool(set(normalized.split("_")) & _SECRET_PARTS)
        or any(part in normalized for part in ("api_key", "private_key", "id_card"))
    )


def _value_end(text: str, start: int, *, header: bool = False) -> int:
    """Consume quoted/structured values, including truncated diagnostic strings."""
    if start == len(text):
        return start
    quote = text[start] if text[start] in "\"'" else ""
    depth = 0
    structured = text[start] in "{["
    for index in range(start + bool(quote), len(text)):
        char = text[index]
        if quote:
            # An odd number of preceding slashes escapes a quote.
            slashes = 0
            previous = index - 1
            while previous >= start and text[previous] == "\\":
                slashes += 1
                previous -= 1
            if char == quote and slashes % 2 == 0:
                quote = ""
                if not structured:
                    return index + 1
        elif structured:
            if char in "\"'":
                quote = char
            elif char in "{[":
                depth += 1
            elif char in "}]":
                depth -= 1
                if depth == 0:
                    return index + 1
        elif char in ("\r\n}]" if header else " \t\r\n,;&}]"):
            return index
    return len(text)


def _redact_url(match: re.Match[str]) -> str:
    value = match.group()
    try:
        parsed = urlsplit(value)
        netloc = parsed.netloc.rsplit("@", 1)[-1]
        if "@" in parsed.netloc:
            netloc = "***:***@" + netloc
        query = parse_qsl(parsed.query, keep_blank_values=True)
        if any(is_sensitive_key(key) for key, _ in query):
            encoded = urlencode(
                [(key, REDACTED if is_sensitive_key(key) else item) for key, item in query]
            )
        else:
            encoded = parsed.query
        return urlunsplit((parsed.scheme, netloc, parsed.path, encoded, parsed.fragment))
    except ValueError:
        return "[invalid URL omitted]"


def redact_text(value: str) -> str:
    """Redact before truncating; quoted JSON and Python repr are both handled."""
    if value.lstrip().startswith(("{", "[")):
        try:
            structured = json.loads(value)
        except (ValueError, RecursionError):
            pass
        else:
            return json.dumps(redact_sensitive(structured), ensure_ascii=False)
    value = _URL.sub(_redact_url, value)
    value = re.sub(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+", r"\1 ***", value)
    output = []
    cursor = 0
    for match in _KEY_VALUE.finditer(value):
        if match.start() < cursor or not is_sensitive_key(match["key"]):
            continue
        start = match.end()
        end = _value_end(
            value,
            start,
            header=any(part in match["key"].lower() for part in ("cookie", "authorization")),
        )
        output.extend(
            (
                value[cursor:start],
                '"***"'
                if start < len(value) and value[start] == '"'
                else "'***'"
                if start < len(value) and value[start] == "'"
                else REDACTED,
            )
        )
        cursor = end
    output.append(value[cursor:])
    return "".join(output)


def redact_sensitive(value: Any, *, omit_keys: bool = False) -> Any:
    """Return a sanitized copy without mutating request or assertion inputs."""
    if isinstance(value, Mapping):
        location = value.get("loc")
        sensitive_input = isinstance(location, (list, tuple)) and any(
            is_sensitive_key(str(part)) for part in location
        )
        result = {}
        for key, item in value.items():
            sensitive = is_sensitive_key(str(key)) or (sensitive_input and key in {"input", "ctx"})
            if sensitive and omit_keys:
                continue
            result[str(key)] = (
                REDACTED if sensitive else redact_sensitive(item, omit_keys=omit_keys)
            )
        return result
    if isinstance(value, (list, tuple, set)):
        return [redact_sensitive(item, omit_keys=omit_keys) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


class RedactingFilter(logging.Filter):
    """Sanitize formatted messages and exception text before handlers emit them."""

    def filter(self, record: logging.LogRecord) -> bool:
        # HTTP transport/SDK debug records contain arbitrary request bodies and
        # byte-pair headers, which cannot reliably be parsed as diagnostic text.
        if record.levelno < logging.INFO and record.name.startswith(("httpcore.", "openai.")):
            record.msg = "HTTP transport/SDK debug details omitted"
            record.args = ()
            record.exc_info = record.exc_text = record.stack_info = None
            return True
        record.msg = redact_text(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact_text("".join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info)
        return True


def safe_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(item, RedactingFilter) for item in logger.filters):
        logger.addFilter(RedactingFilter())
    return logger


def protect_http_logs() -> None:
    """Protect dependency loggers at HTTP/LLM entry points, including direct use."""
    # Logger filters do not propagate to children; use the actual emitter names.
    for name in (
        "httpx",
        "httpcore.connection",
        "httpcore.http11",
        "httpcore.http2",
        "httpcore.proxy",
        "httpcore.socks",
        "openai._base_client",
    ):
        safe_logger(name)


def safe_task_error(error: Exception) -> Exception:
    """Do not hand raw exceptions/arguments to Celery's logs and result backend."""
    message = redact_text(str(error))
    if type(error) in {
        ValueError,
        TypeError,
        RuntimeError,
        ConnectionError,
        TimeoutError,
        LookupError,
    }:
        return type(error)(message)
    return RuntimeError(f"{type(error).__name__}: {message}")
