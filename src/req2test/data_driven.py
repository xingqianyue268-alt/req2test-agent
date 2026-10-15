"""Strict JSON/CSV rows expanded into existing HttpTestSpec objects, without I/O."""

from __future__ import annotations

import base64
import binascii
import csv
import io
import json
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .execution_models import ExecutionConfig, HttpTestSpec
from .security.execution import validate_execution_target


class DatasetUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str
    content_base64: str


class DataDrivenPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template: HttpTestSpec
    dataset: DatasetUpload
    base_url: str
    run_http_tool: bool = True
    run_pytest: bool = True
    mock_isolation: bool = False
    mock_seed: list[dict] = Field(default_factory=list, max_length=20)


class DatasetError(ValueError):
    """Safe actionable error which never embeds a data cell."""


def _json(text):
    def constant(_):
        raise DatasetError("不允许非标准 JSON 数值")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise DatasetError("JSON 存在重复字段")
            result[key] = value
        return result

    return json.loads(text, parse_constant=constant, object_pairs_hook=pairs)


def expand_dataset(
    template: HttpTestSpec, dataset: DatasetUpload, *, response_schemas: dict | None = None
) -> list[HttpTestSpec]:
    if len(dataset.content_base64) > 1400000:
        raise DatasetError("数据文件不能超过 1 MiB")
    try:
        raw = base64.b64decode(dataset.content_base64, validate=True)
        if len(raw) > 1048576:
            raise DatasetError("数据文件不能超过 1 MiB")
        content = raw.decode("utf-8-sig")
    except (UnicodeError, binascii.Error, ValueError):
        raise DatasetError("数据文件编码无效或超过限制") from None
    filename = dataset.filename.replace("\\", "/").split("/")[-1]
    if filename.lower().endswith(".json"):
        try:
            rows = _json(content)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"JSON 第 {exc.lineno} 行第 {exc.colno} 列格式错误") from None
        except (ValueError, RecursionError):
            raise DatasetError("JSON 数据文件格式错误或存在重复字段") from None
        line_offset = 0
    elif filename.lower().endswith(".csv"):
        try:
            reader = csv.DictReader(io.StringIO(content), strict=True)
            fields = reader.fieldnames or []
            if len(set(fields)) != len(fields):
                raise DatasetError("CSV 存在重复列名")
            rows = []
            for row in reader:
                if None in row or any(v is None for v in row.values()):
                    raise DatasetError(f"CSV 第 {reader.line_num} 行列数错误")
                values = {}
                for key, value in row.items():
                    if value == "":
                        continue
                    try:
                        values[key] = value if key in {"id", "name", "path"} else _json(value)
                    except (ValueError, RecursionError):
                        raise DatasetError(f"CSV 第 {reader.line_num} 行 JSON 单元格无效") from None
                rows.append(values)
                if len(rows) > 20:
                    raise DatasetError("单组数据集最多 20 行")
        except csv.Error:
            raise DatasetError("CSV 格式错误") from None
        line_offset = 1
    else:
        raise DatasetError("仅支持 JSON 或 CSV 数据文件")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise DatasetError("数据文件必须包含 1 至 20 个数据行")
    allowed = {
        "id",
        "name",
        "path",
        "headers",
        "query",
        "json_body",
        "json_body_present",
        "expected_status",
        "expected_json_contains",
        "expected_json_schema",
        "expected_text_contains",
        "assertions",
    }
    seen, cases = set(), []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) - allowed:
            raise DatasetError(f"第 {index + line_offset} 行字段无效")
        identity = row.get("id", "")
        if (
            not isinstance(identity, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identity)
            or identity in seen
        ):
            raise DatasetError(
                f"第 {index + line_offset} 行需唯一的 id（字母、数字、下划线、短横线）"
            )
        seen.add(identity)
        values = template.model_dump()
        values.update({k: v for k, v in row.items() if k != "id"})
        values.update(
            case_id=f"{template.case_id}::{identity}",
            data_id=identity,
            source=f"{filename}:{index + line_offset}",
        )
        if (
            response_schemas is not None
            and "expected_status" in row
            and "expected_json_schema" not in row
        ):
            values["expected_json_schema"] = response_schemas.get(str(row["expected_status"]))
        if "json_body" in row:
            values["json_body_present"] = True
        try:
            cases.append(HttpTestSpec.model_validate(values))
        except (ValidationError, TypeError, RecursionError):
            raise DatasetError(f"第 {index + line_offset} 行测试规格无效") from None
    return cases


def compile_data_plan(plan: DataDrivenPlan) -> ExecutionConfig:
    target = validate_execution_target(plan.base_url)
    if not (plan.run_http_tool or plan.run_pytest):
        raise DatasetError("请至少选择一个执行器")
    if plan.mock_isolation:
        from .mock_lifecycle import validate_mock_target

        validate_mock_target(plan.base_url)
    specs = expand_dataset(plan.template, plan.dataset)
    return ExecutionConfig(
        enabled=True,
        base_url=target,
        api_specs=specs,
        max_executable_cases=len(specs),
        use_llm_planner=False,
        use_llm_failure_analysis=False,
        run_http_tool=plan.run_http_tool,
        run_pytest=plan.run_pytest,
        mock_isolation=plan.mock_isolation,
        mock_seed=plan.mock_seed,
    )
