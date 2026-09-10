"""Load and discover immutable golden evaluation dataset snapshots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from .models import GoldenDataset, GoldenDatasetCase

MAX_DATASET_BYTES = 5 * 1024 * 1024


class DatasetLoadError(ValueError):
    """A golden dataset is unreadable, inconsistent, or violates its schema."""


def load_golden_dataset(path: str | Path) -> GoldenDataset:
    dataset_path = Path(path).expanduser().resolve()
    if not dataset_path.is_file():
        raise DatasetLoadError(f"Golden dataset does not exist: {dataset_path}")
    if dataset_path.suffix.lower() != ".jsonl":
        raise DatasetLoadError("Golden dataset must use the .jsonl format")

    raw = dataset_path.read_bytes()
    if not raw:
        raise DatasetLoadError("Golden dataset must not be empty")
    if len(raw) > MAX_DATASET_BYTES:
        raise DatasetLoadError(
            f"Golden dataset exceeds the {MAX_DATASET_BYTES}-byte safety limit"
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DatasetLoadError("Golden dataset must be UTF-8 encoded") from exc

    records: list[GoldenDatasetCase] = []
    for line_number, source_line in enumerate(text.splitlines(), start=1):
        line = source_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetLoadError(
                f"Invalid JSON on line {line_number}: {exc.msg}"
            ) from exc
        try:
            records.append(GoldenDatasetCase.model_validate(payload))
        except ValidationError as exc:
            raise DatasetLoadError(
                f"Invalid golden record on line {line_number}: {exc}"
            ) from exc

    if not records:
        raise DatasetLoadError("Golden dataset must contain at least one record")

    record_ids = [record.id for record in records]
    if len(record_ids) != len(set(record_ids)):
        duplicates = sorted({item for item in record_ids if record_ids.count(item) > 1})
        raise DatasetLoadError(f"Golden dataset contains duplicate ids: {duplicates}")

    versions = {record.dataset_version for record in records}
    if len(versions) != 1:
        raise DatasetLoadError(
            f"Golden dataset must contain exactly one dataset_version, found: {sorted(versions)}"
        )

    return GoldenDataset(
        path=dataset_path,
        name=dataset_path.stem,
        dataset_version=next(iter(versions)),
        digest=hashlib.sha256(raw).hexdigest(),
        cases=records,
    )


def discover_golden_datasets(root: str | Path) -> list[GoldenDataset]:
    dataset_root = Path(root).expanduser().resolve()
    if not dataset_root.is_dir():
        return []
    return [load_golden_dataset(path) for path in sorted(dataset_root.glob("*.jsonl"))]
