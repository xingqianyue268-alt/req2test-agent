"""Local response schema assertions shared by both executors."""

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


def schema_failures(payload, schema):
    # Imported schemas have already been expanded offline. Never resolve external references,
    # including when an API caller constructs HttpTestSpec directly.
    def check(value, depth=0):
        if depth > 40:
            raise ValueError("响应 Schema 嵌套过深")
        if isinstance(value, dict):
            if any(key in value for key in ("$ref", "$dynamicRef", "$recursiveRef")):
                raise ValueError("响应 Schema 必须在导入时完成本地引用展开")
            for child in value.values():
                check(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                check(child, depth + 1)

    check(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        raise ValueError("响应 Schema 无效") from None
    # Error messages contain neither actual nor expected values (credentials may be present).
    return [
        "响应 JSON 不符合 Schema："
        + str(error.validator)
        + "，路径 /"
        + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in error.absolute_path)
        for error in Draft202012Validator(schema).iter_errors(payload)
    ][:20]
