from __future__ import annotations

import json
from pathlib import Path

import pytest

from req2test.evaluation.dataset import (
    DatasetLoadError,
    discover_golden_datasets,
    load_golden_dataset,
)


def _record(record_id="case-1", version="dataset-v1"):
    return {
        "id": record_id,
        "requirement_text": "用户可以登录系统。",
        "expected_requirements": [
            {"id": "REQ-1", "text": "登录", "keywords": ["用户", "登录"]}
        ],
        "expected_constraints": [],
        "tags": ["Demo"],
        "dataset_version": version,
    }


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )


def test_load_golden_dataset_validates_version_ids_and_digest(tmp_path: Path):
    path = tmp_path / "golden.jsonl"
    _write_jsonl(path, [_record("case-1"), _record("case-2")])

    dataset = load_golden_dataset(path)

    assert dataset.dataset_version == "dataset-v1"
    assert dataset.name == "golden"
    assert len(dataset.digest) == 64
    assert [item.id for item in dataset.cases] == ["case-1", "case-2"]
    assert dataset.cases[0].tags == ["demo"]
    assert discover_golden_datasets(tmp_path) == [dataset]


@pytest.mark.parametrize(
    ("records", "message"),
    [
        ([_record("duplicate"), _record("duplicate")], "duplicate ids"),
        ([_record("one", "v1"), _record("two", "v2")], "exactly one dataset_version"),
        ([{**_record(), "unexpected": True}], "Invalid golden record"),
    ],
)
def test_load_golden_dataset_rejects_inconsistent_or_unknown_data(
    tmp_path: Path, records: list[dict], message: str
):
    path = tmp_path / "invalid.jsonl"
    _write_jsonl(path, records)

    with pytest.raises(DatasetLoadError, match=message):
        load_golden_dataset(path)


def test_load_golden_dataset_reports_line_number_and_requires_jsonl(tmp_path: Path):
    bad_json = tmp_path / "bad.jsonl"
    bad_json.write_text("{}\nnot-json\n", encoding="utf-8")
    with pytest.raises(DatasetLoadError, match="line 1"):
        load_golden_dataset(bad_json)

    wrong_suffix = tmp_path / "golden.json"
    wrong_suffix.write_text("[]", encoding="utf-8")
    with pytest.raises(DatasetLoadError, match=".jsonl"):
        load_golden_dataset(wrong_suffix)


def test_public_demo_dataset_is_valid_and_contains_no_credential_fields():
    dataset = load_golden_dataset("evals/golden_demo.jsonl")

    assert dataset.dataset_version == "golden-demo-v1"
    assert len(dataset.cases) >= 3
    serialized = dataset.model_dump_json().lower()
    assert "api_key" not in serialized
    assert "authorization" not in serialized
    assert "password_hash" not in serialized
