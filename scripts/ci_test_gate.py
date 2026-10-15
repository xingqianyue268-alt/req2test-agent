"""Fail closed on missing tests, failures, errors or skips; preserve a safe summary."""

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def summarize(path):
    try:
        root = ET.parse(path).getroot()
        cases = root.findall(".//testcase")
        totals = {"tests": len(cases), "failed": 0, "errors": 0, "skipped": 0, "passed": 0}
        for case in cases:
            if case.find("error") is not None:
                totals["errors"] += 1
            elif case.find("failure") is not None:
                totals["failed"] += 1
            elif case.find("skipped") is not None:
                totals["skipped"] += 1
            else:
                totals["passed"] += 1
        totals["status"] = (
            "passed"
            if cases and not any(totals[k] for k in ("failed", "errors", "skipped"))
            else "rejected"
        )
        return totals
    except (OSError, ET.ParseError):
        return {
            "status": "report_unavailable",
            "tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "skipped": 0,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="artifacts/pytest.xml")
    parser.add_argument("--output", default="artifacts/test-summary.json")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        import os

        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import SQLAlchemyError

        try:
            engine = create_engine(
                os.environ["REQ2TEST_TEST_DATABASE_URL"], connect_args={"connect_timeout": 5}
            )
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            summary = {"status": "passed", "postgres": "available"}
        except (
            KeyError,
            SQLAlchemyError,
            OSError,
        ):  # Credentials and raw connection exceptions never enter CI artifacts.
            summary = {"status": "environment_unavailable", "postgres": "unavailable"}
    else:
        summary = summarize(args.report)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
