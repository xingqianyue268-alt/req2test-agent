"""JUnit XML from durable execution evidence, without inventing successful cases."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

from .security.redaction import redact_sensitive


def _text(value):
    text = str(value)
    return re.sub(r"[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]", "�", text)


def to_junit_xml(execution: dict, *, truncated: bool = False) -> str:
    data = redact_sensitive(execution)
    root = ET.Element("testsuites")
    suite = ET.SubElement(
        root,
        "testsuite",
        name="Req2Test",
        tests="0",
        failures="0",
        errors="0",
        skipped="0",
        time="0",
    )
    properties = ET.SubElement(suite, "properties")
    for name, value in (data.get("summary") or {}).items():
        ET.SubElement(properties, "property", name=_text(name), value=_text(value))
    rows = [("http", row) for row in data.get("http_results", [])]
    pytest_result = data.get("pytest_result")
    if pytest_result:
        rows.extend(("pytest", row) for row in pytest_result.get("case_results", []))
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    duration = 0.0

    def special(name, kind, message):
        totals["tests"] += 1
        totals[{"error": "errors", "skipped": "skipped", "failure": "failures"}[kind]] += 1
        node = ET.SubElement(suite, "testcase", classname="Req2Test.runtime", name=name, time="0")
        ET.SubElement(
            node, kind, message=_text(message), type="infrastructure" if kind == "error" else kind
        ).text = _text(message)

    for executor, row in rows:
        totals["tests"] += 1
        seconds = max(0, float(row.get("duration_ms") or 0)) / 1000
        duration += seconds
        node = ET.SubElement(
            suite,
            "testcase",
            classname=f"Req2Test.{executor}",
            name=_text(row.get("case_id", "unknown")),
            time=f"{seconds:.6f}",
        )
        props = ET.SubElement(node, "properties")
        for name in (
            "data_id",
            "source",
            "method",
            "url",
            "expected_status",
            "status_code",
            "execution_mode",
        ):
            ET.SubElement(props, "property", name=name, value=_text(row.get(name, "")))
        if not row.get("passed"):
            kind = "error" if row.get("error") or row.get("timed_out") else "failure"
            totals["errors" if kind == "error" else "failures"] += 1
            category = (
                "timeout"
                if row.get("timed_out")
                else "connectivity"
                if row.get("error")
                else "assertion_failure"
            )
            message = "; ".join(row.get("failures") or []) or row.get("error") or "Test failed"
            ET.SubElement(node, kind, type=category, message=_text(message)).text = _text(
                json.dumps(
                    {
                        "request": row.get("request", {}),
                        "expected_status": row.get("expected_status"),
                        "actual_status": row.get("status_code"),
                        "assertions": row.get("assertions", []),
                        "response_excerpt": row.get("response_excerpt", ""),
                        "error": row.get("error"),
                    },
                    ensure_ascii=False,
                )
            )
        ET.SubElement(node, "system-out").text = _text(
            json.dumps(
                {
                    "data_id": row.get("data_id"),
                    "source": row.get("source"),
                    "execution_mode": row.get("execution_mode", "live"),
                    "assertions": row.get("assertions", []),
                },
                ensure_ascii=False,
            )
        )
    if pytest_result:
        recorded = {r.get("case_id") for r in pytest_result.get("case_results", [])}
        expected = {r.get("case_id") for r in data.get("executable_cases", [])}
        for case_id in sorted(expected - recorded):
            special("pytest::" + str(case_id), "error", "Pytest 未完成或未保留该数据行结果")
        if (
            not pytest_result.get("passed")
            and not any(not r.get("passed") for r in pytest_result.get("case_results", []))
            and not (expected - recorded)
        ):
            special("pytest-runtime", "error", "Pytest 运行器失败或超时")
    lifecycle = data.get("lifecycle") or {}
    if lifecycle and (lifecycle.get("setup") != "passed" or lifecycle.get("cleanup") != "passed"):
        special("mock-lifecycle", "error", lifecycle.get("error", "Mock 数据准备或清理未完成"))
    if truncated:
        special("evidence-truncated", "error", "持久化证据被截断，不能确认完整测试集合")
    if not rows and not totals["tests"]:
        status = (data.get("summary") or {}).get("status")
        special(
            "execution",
            "skipped" if status in {"disabled", "skipped"} else "error",
            "没有完整执行证据",
        )
    for key, value in totals.items():
        suite.set(key, str(value))
        root.set(key, str(value))
    suite.set("time", f"{duration:.6f}")
    root.set("time", f"{duration:.6f}")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
