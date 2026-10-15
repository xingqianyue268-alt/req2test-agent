"""Bounded, offline OpenAPI 3.0/3.1 import into existing executable contracts.

No URI is fetched. Unsupported operations remain visible but cannot be executed.
Examples are synthetic starting points; users must review data and authorization.
"""

from __future__ import annotations

import base64
import binascii
import copy
import json
import math
import re
from typing import Any
from urllib.parse import quote

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field

from .data_driven import DatasetUpload, expand_dataset
from .execution_models import ExecutionConfig, HttpTestSpec
from .security.execution import validate_execution_target

MAX_BYTES = 1024 * 1024
METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
ANNOTATIONS = {
    "title",
    "description",
    "example",
    "examples",
    "default",
    "deprecated",
    "readOnly",
    "writeOnly",
    "xml",
    "externalDocs",
}
SCHEMA_KEYS = ANNOTATIONS | {
    "type",
    "properties",
    "required",
    "items",
    "enum",
    "const",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "uniqueItems",
    "additionalProperties",
    "nullable",
}


class ContractImportError(ValueError):
    """A document cannot safely be converted to an executable contract."""


class ContractPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str
    content_base64: str
    selected_operations: list[str] = Field(default_factory=list)
    base_url: str
    headers: dict[str, str] = Field(default_factory=dict)
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    datasets: dict[str, DatasetUpload] = Field(default_factory=dict)
    include_validation: bool = True
    run_http_tool: bool = True
    run_pytest: bool = True


def decode_upload(content_base64: str) -> bytes:
    if len(content_base64) > (MAX_BYTES * 4 // 3 + 4):
        raise ContractImportError("OpenAPI 文件不能超过 1 MiB")
    try:
        return base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise ContractImportError("OpenAPI 文件编码无效") from None


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractImportError("文档含重复字段")
        result[key] = value
    return result


class _Loader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    pairs = []
    for key, value in node.value:
        name = loader.construct_object(key, deep=True)
        if not isinstance(name, (str, int)):
            raise ContractImportError("YAML 字段名必须为字符串或响应状态码")
        pairs.append((str(name), loader.construct_object(value, deep=True)))
    return _unique_pairs(pairs)


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _load(filename: str, content: bytes) -> dict:
    if len(content) > MAX_BYTES:
        raise ContractImportError("OpenAPI 文件不能超过 1 MiB")
    try:
        text = content.decode("utf-8-sig")
        if filename.lower().endswith(".json"):
            doc = json.loads(
                text,
                object_pairs_hook=_unique_pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("非标准 JSON 数值")),
            )
        elif filename.lower().endswith((".yaml", ".yml")):
            # Reject aliases before construction (including recursive / expansion bombs).
            depth = 0
            for event in yaml.parse(text, Loader=_Loader):
                if isinstance(event, yaml.AliasEvent):
                    raise ContractImportError("YAML alias 不受支持，请使用 OpenAPI 本地 $ref")
                if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                    depth += 1
                elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                    depth -= 1
                if depth > 40:
                    raise ContractImportError("OpenAPI 嵌套超过 40 层")
            doc = yaml.load(text, Loader=_Loader)
        else:
            raise ContractImportError("仅支持 .json、.yaml、.yml 文件")
    except (UnicodeError, json.JSONDecodeError, yaml.YAMLError, RecursionError) as exc:
        mark = getattr(exc, "problem_mark", None)
        line = getattr(exc, "lineno", None) or (mark.line + 1 if mark else 1)
        column = getattr(exc, "colno", None) or (mark.column + 1 if mark else 1)
        raise ContractImportError(f"OpenAPI 解析错误：第 {line} 行，第 {column} 列") from None
    nodes = 0

    def check(value, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 30000 or depth > 40:
            raise ContractImportError("OpenAPI 文档复杂度超过限制")
        if isinstance(value, dict):
            for item in value.values():
                check(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                check(item, depth + 1)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ContractImportError("文档不允许 NaN 或 Infinity")
        elif value is not None and not isinstance(value, (str, bool, float, int)):
            raise ContractImportError("文档必须使用 JSON 兼容类型；YAML 日期请加引号")

    check(doc)
    if not isinstance(doc, dict) or not re.fullmatch(r"3\.(0|1)\.\d+", str(doc.get("openapi", ""))):
        raise ContractImportError("本阶段支持 OpenAPI 3.0.x / 3.1.x")
    if not isinstance(doc.get("paths"), dict):
        raise ContractImportError("OpenAPI paths 必须为对象")
    return doc


class _Resolver:
    def __init__(self, doc):
        self.doc = doc
        self.nodes = 0

    def resolve(self, value, trail=(), depth=0):
        self.nodes += 1
        if depth > 30 or self.nodes > 20000:
            raise ContractImportError("引用展开超过限制")
        if isinstance(value, list):
            return [self.resolve(v, trail, depth + 1) for v in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            ref = value["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/components/"):
                raise ContractImportError("仅支持 #/components/ 下的本地引用；不会获取远端资源")
            if ref in trail:
                raise ContractImportError("循环引用不支持自动生成")
            if set(value) - {"$ref", "description", "summary"}:
                raise ContractImportError("$ref 的断言类同级字段不支持自动生成")
            target = self.doc
            try:
                for part in ref[2:].split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
            except (KeyError, TypeError):
                raise ContractImportError("本地引用不存在") from None
            return self.resolve(target, (*trail, ref), depth + 1)
        return {k: self.resolve(v, trail, depth + 1) for k, v in value.items()}


def _schema(schema):
    if not isinstance(schema, dict):
        raise ContractImportError("Schema 必须是对象")
    unknown = set(schema) - SCHEMA_KEYS
    if unknown:
        # No user-controlled values in diagnostic text.
        raise ContractImportError("Schema 含未支持的约束（如组合、pattern、format 或条件约束）")
    result = {k: copy.deepcopy(v) for k, v in schema.items() if k not in ANNOTATIONS | {"nullable"}}
    if not result:
        return {}
    kind = result.get("type")
    if kind is None:
        kind = "object" if "properties" in result else None
        if kind:
            result["type"] = kind
    kinds = kind if isinstance(kind, list) else [kind]
    if not kinds or any(
        k not in {"object", "array", "string", "integer", "number", "boolean", "null"}
        for k in kinds
    ):
        raise ContractImportError("Schema 需要明确的受支持 type")
    if schema.get("nullable"):
        result["type"] = list(dict.fromkeys([*kinds, "null"]))
    for bound in ("Minimum", "Maximum"):
        exclusive = "exclusive" + bound
        if isinstance(result.get(exclusive), bool):
            enabled = result.pop(exclusive)
            if enabled:
                if bound.lower() not in result:
                    raise ContractImportError("exclusive bound 缺少对应数值边界")
                result[exclusive] = result.pop(bound.lower())
    if "properties" in result:
        result["properties"] = {k: _schema(v) for k, v in result["properties"].items()}
    if "items" in result:
        result["items"] = _schema(result["items"])
    if "array" in kinds and "items" not in result:
        raise ContractImportError("数组 Schema 必须声明 items")
    if isinstance(result.get("additionalProperties"), dict):
        result["additionalProperties"] = _schema(result["additionalProperties"])
    try:
        Draft202012Validator.check_schema(result)
    except SchemaError:
        raise ContractImportError("Schema 约束格式错误") from None
    # Retain examples for input generation, not response equality assertions.
    for key in ("example", "default", "readOnly", "writeOnly"):
        if key in schema:
            result[key] = copy.deepcopy(schema[key])
    return result


def _json_schema(content):
    if not content:
        return None
    if "application/json" not in content:
        raise ContractImportError("本阶段只执行 application/json 请求体及响应")
    media = content["application/json"]
    result = _schema(media["schema"])
    if "example" in media:
        result["example"] = media["example"]
    return result


def _operation(doc, path, method, raw, inherited):
    resolved = _Resolver(doc).resolve(raw)
    parameters = {}
    for param in [*_Resolver(doc).resolve(inherited), *resolved.get("parameters", [])]:
        location = param["in"]
        if location not in {"path", "query", "header"}:
            raise ContractImportError("暂不支持 cookie 参数；可显式配置 Cookie 请求头")
        schema = _schema(param["schema"])
        if schema["type"] not in {"string", "integer", "number", "boolean"}:
            raise ContractImportError("参数暂只支持简单标量；对象和数组序列化需后续支持")
        if param.get("style", "simple" if location in {"path", "header"} else "form") not in {
            "simple",
            "form",
        }:
            raise ContractImportError("参数序列化 style 暂不支持")
        if "example" in param:
            schema["example"] = param["example"]
        parameters[(location, param["name"])] = {
            "name": param["name"],
            "in": location,
            "required": location == "path" or bool(param.get("required")),
            "schema": schema,
        }
    required_paths = set(re.findall(r"\{([^}]+)\}", path))
    if required_paths != {name for (loc, name) in parameters if loc == "path"}:
        raise ContractImportError("路径模板和 path 参数声明不一致")
    responses = {}
    for code, response in resolved["responses"].items():
        if re.fullmatch(r"[1-5]\d\d", str(code)):
            responses[str(code)] = {
                "description": response.get("description", ""),
                "schema": _json_schema(response.get("content")),
            }
    if not any(200 <= int(code) < 300 for code in responses):
        raise ContractImportError("需声明明确的 2xx 成功响应；default/范围响应不用于自动生成")
    body = resolved.get("requestBody", {})
    return {
        "key": f"{method.upper()} {path}",
        "method": method.upper(),
        "path": path,
        "operation_id": resolved.get("operationId", ""),
        "summary": resolved.get("summary", ""),
        "parameters": list(parameters.values()),
        "request_schema": _json_schema(body.get("content")),
        "body_required": bool(body.get("required")),
        "responses": responses,
        "security": resolved.get("security", doc.get("security", [])),
        "supported": True,
        "issues": [],
    }


def parse_document(filename: str, content: bytes) -> dict:
    doc = _load(filename, content)
    operations = []
    for path, item in doc["paths"].items():
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or path.startswith("//")
            or any(c in path for c in ("?", "#", "\\", "\r", "\n"))
        ):
            raise ContractImportError("OpenAPI path 必须是安全的相对路径模板")
        if not isinstance(item, dict):
            raise ContractImportError("Path Item 必须是对象")
        for method, raw in item.items():
            if method not in METHODS:
                continue
            try:
                operations.append(_operation(doc, path, method, raw, item.get("parameters", [])))
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                reason = (
                    str(exc) if isinstance(exc, ValueError) else "接口结构缺少字段或字段类型错误"
                )
                operations.append(
                    {
                        "key": f"{method.upper()} {path}",
                        "method": method.upper(),
                        "path": path,
                        "supported": False,
                        "issues": [reason],
                    }
                )
            if len(operations) > 200:
                raise ContractImportError("单文档最多支持 200 个接口")
    if not operations:
        raise ContractImportError("文档没有可识别的接口；Path Item $ref 暂不支持")
    return {
        "openapi": doc["openapi"],
        "operations": operations,
        "warnings": [
            "仅解析文件，不访问 servers 地址。请明确选择接口、目标及认证，并检查样例数据。",
            "组合 Schema、循环/外部引用、format/pattern、复杂参数序列化不自动执行；不完整支持全部 OpenAPI 特性。",
        ],
    }


def _sample(schema):
    if not schema:
        return "demo"
    for key in ("example", "default", "const"):
        if key in schema:
            value = copy.deepcopy(schema[key])
            break
    else:
        if "enum" in schema:
            value = copy.deepcopy(schema["enum"][0])
        else:
            kind = schema["type"]
            kind = (
                next((k for k in kind if k != "null"), "null") if isinstance(kind, list) else kind
            )
            if kind == "object":
                value = {
                    key: _sample(child)
                    for key, child in schema.get("properties", {}).items()
                    if not child.get("readOnly")
                }
            elif kind == "array":
                size = max(1, schema.get("minItems", 0))
                if size > 20:
                    raise ContractImportError("样例数组超过 20 项，请提供请求体覆盖值")
                value = [_sample(schema["items"]) for _ in range(size)]
            elif kind == "string":
                size = max(4, schema.get("minLength", 0))
                size = min(size, schema.get("maxLength", size))
                if size > 1024:
                    raise ContractImportError("样例字符串过长，请提供覆盖值")
                value = ("demo" * (size // 4 + 1))[:size]
            elif kind in {"integer", "number"}:
                value = max(1, schema.get("minimum", 1))
                if "exclusiveMinimum" in schema:
                    value = max(value, schema["exclusiveMinimum"] + 1)
                if "maximum" in schema:
                    value = min(value, schema["maximum"])
                if "exclusiveMaximum" in schema:
                    value = min(value, schema["exclusiveMaximum"] - 1)
            elif kind == "boolean":
                value = True
            else:
                value = None
    if not Draft202012Validator(schema).is_valid(value):
        raise ContractImportError("无法为约束生成有效样例，请提供匹配 Schema 的覆盖值")
    return value


def compile_plan(plan: ContractPlan) -> ExecutionConfig:
    try:
        target = validate_execution_target(plan.base_url)
    except ValueError:
        raise ContractImportError("目标地址必须为白名单内、无凭据的有效 HTTP(S) 地址") from None
    try:
        return _compile_plan(plan, target)
    except ContractImportError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        # Native conversion/Pydantic errors may echo arbitrary credential-bearing values.
        raise ContractImportError("OpenAPI 计划字段或样例数据无效，请检查接口覆盖配置") from None


def _compile_plan(plan: ContractPlan, target: str) -> ExecutionConfig:
    if not plan.selected_operations:
        raise ContractImportError("请至少选择一个接口")
    if not (plan.run_http_tool or plan.run_pytest):
        raise ContractImportError("请至少选择一个执行器")
    catalog = parse_document(plan.filename, decode_upload(plan.content_base64))
    operations = {op["key"]: op for op in catalog["operations"]}
    specs = []
    for key in dict.fromkeys(plan.selected_operations):
        if key not in operations or not operations[key]["supported"]:
            raise ContractImportError("所选接口不存在或包含未支持的契约，请查看导入诊断")
        op = operations[key]
        overrides = plan.overrides.get(key, {})
        if set(overrides) - {
            "path",
            "query",
            "headers",
            "json_body",
            "expected_status",
            "expected_json_contains",
        }:
            raise ContractImportError("接口覆盖值包含未知字段")
        path, query, headers = op["path"], {}, dict(plan.headers)
        for parameter in op["parameters"]:
            location, name = parameter["in"], parameter["name"]
            values = overrides.get(
                {"path": "path", "query": "query", "header": "headers"}[location], {}
            )
            if name in values:
                value = values[name]
            elif location == "header" and any(k.lower() == name.lower() for k in headers):
                value = next(v for k, v in headers.items() if k.lower() == name.lower())
                headers = {k: v for k, v in headers.items() if k.lower() != name.lower()}
            else:
                value = _sample(parameter["schema"])
            if not Draft202012Validator(parameter["schema"]).is_valid(value):
                raise ContractImportError("参数覆盖值不符合 Schema")
            if location == "path":
                path = path.replace("{" + name + "}", quote(str(value), safe=""))
            elif location == "query":
                query[name] = str(value).lower() if isinstance(value, bool) else value
            else:
                headers[name] = str(value)
        headers.update(overrides.get("headers", {}))
        query.update(overrides.get("query", {}))
        schema = op["request_schema"]
        body = (
            overrides.get("json_body")
            if "json_body" in overrides
            else (_sample(schema) if schema else None)
        )
        if schema and not Draft202012Validator(schema).is_valid(body):
            raise ContractImportError("请求体覆盖值不符合 Schema")
        code = int(
            overrides.get(
                "expected_status", min(int(c) for c in op["responses"] if 200 <= int(c) < 300)
            )
        )
        if str(code) not in op["responses"]:
            raise ContractImportError("预期状态码必须在契约响应中声明")
        positive = HttpTestSpec(
            case_id=f"OAS-{len(specs) + 1:03d}",
            name=key + " 正向",
            method=op["method"],
            path=path,
            headers=headers,
            query=query,
            json_body=body,
            json_body_present=schema is not None,
            expected_status=code,
            expected_json_contains=overrides.get("expected_json_contains", {}),
            expected_json_schema=op["responses"][str(code)]["schema"],
        )
        if key in plan.datasets:
            specs.extend(
                expand_dataset(
                    positive,
                    plan.datasets[key],
                    response_schemas={
                        status: response["schema"] for status, response in op["responses"].items()
                    },
                )
            )
            if len(specs) > 20:
                raise ContractImportError("生成用例超过单任务 20 条限制")
            continue
        specs.append(positive)
        error_code = next((c for c in (422, 400) if str(c) in op["responses"]), None)
        if plan.include_validation and error_code:
            variants = []
            if isinstance(body, dict) and schema:
                for required in schema.get("required", []):
                    invalid = copy.deepcopy(body)
                    invalid.pop(required, None)
                    variants.append(("缺少必填字段", {"json_body": invalid}))
                if schema.get("properties"):
                    name, field = next(iter(schema["properties"].items()))
                    invalid = copy.deepcopy(body)
                    invalid[name] = [] if field["type"] != "array" else {}
                    if not Draft202012Validator(field).is_valid(invalid[name]):
                        variants.append(("字段类型错误", {"json_body": invalid}))
            for param in op["parameters"]:
                if param["in"] == "query" and param["required"]:
                    invalid_query = dict(query)
                    invalid_query.pop(param["name"], None)
                    variants.append(("缺少必填查询参数", {"query": invalid_query}))
            for label, changes in variants:
                specs.append(
                    positive.model_copy(
                        deep=True,
                        update={
                            **changes,
                            "case_id": f"OAS-{len(specs) + 1:03d}",
                            "name": key + " " + label,
                            "expected_status": error_code,
                            "expected_json_contains": {},
                            "expected_json_schema": op["responses"][str(error_code)]["schema"],
                        },
                    )
                )
        if len(specs) > 20:
            raise ContractImportError("生成用例超过单任务 20 条限制，请减少接口选择或关闭校验用例")
    return ExecutionConfig(
        enabled=True,
        base_url=target,
        api_specs=specs,
        max_executable_cases=len(specs),
        use_llm_planner=False,
        use_llm_failure_analysis=False,
        run_http_tool=plan.run_http_tool,
        run_pytest=plan.run_pytest,
    )
