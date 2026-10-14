"""Offline contract parsing, selection and security regression tests."""

import json

import pytest
import yaml

from req2test.openapi_import import ContractPlan, compile_plan, parse_document


def document():
    return {
        "openapi": "3.1.0",
        "info": {"title": "Synthetic API", "version": "1"},
        "servers": [{"url": "https://untrusted.invalid"}],
        "components": {
            "schemas": {
                "Product": {
                    "type": "object",
                    "required": ["name", "count"],
                    "properties": {
                        "name": {"type": "string", "enum": ["demo"]},
                        "count": {"type": "integer", "minimum": 1},
                        "meta": {"type": "object", "properties": {"active": {"type": "boolean"}}},
                    },
                }
            }
        },
        "paths": {
            "/products": {
                "post": {
                    "operationId": "createProduct",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Product"}}
                        },
                    },
                    "responses": {
                        "201": {
                            "description": "created",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Product"}
                                }
                            },
                        },
                        "422": {"description": "invalid"},
                    },
                }
            },
            "/users/{id}": {
                "get": {
                    "parameters": [
                        {
                            "in": "path",
                            "name": "id",
                            "required": True,
                            "schema": {"type": "integer", "minimum": 1},
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    }


def plan(doc=None, **kwargs):
    return ContractPlan(
        filename="api.json",
        content_base64=__import__("base64")
        .b64encode(json.dumps(doc or document()).encode())
        .decode(),
        selected_operations=["POST /products"],
        base_url="http://127.0.0.1:8081",
        **kwargs,
    )


@pytest.mark.parametrize("fmt", ["json", "yaml"])
def test_catalog_and_selected_specs(fmt):
    doc = document()
    raw = json.dumps(doc) if fmt == "json" else yaml.safe_dump(doc)
    catalog = parse_document("api." + fmt, raw.encode())
    assert len(catalog["operations"]) == 2
    assert all(op["supported"] for op in catalog["operations"])
    config = compile_plan(plan())
    assert config.enabled and config.run_http_tool and config.run_pytest
    assert len(config.api_specs) == 4  # positive, each required field missing, wrong type
    assert config.api_specs[0].expected_status == 201
    assert config.api_specs[0].json_body["count"] == 1
    assert config.api_specs[0].expected_json_schema["required"] == ["name", "count"]
    assert all(s.path == "/products" for s in config.api_specs)
    assert all(s.expected_status == 422 for s in config.api_specs[1:])


@pytest.mark.parametrize(
    "schema",
    [
        {"$ref": "https://evil.invalid/schema"},
        {"$ref": "file:///etc/passwd"},
        {"$ref": "#/components/schemas/Product"},
        {"oneOf": [{"type": "string"}, {"type": "integer"}]},
        {"allOf": [{"type": "object"}]},
        {"anyOf": [{"type": "string"}]},
    ],
)
def test_unsupported_reference_or_composition_blocks_execution(schema):
    doc = document()
    doc["components"]["schemas"]["Product"] = schema
    catalog = parse_document("a.json", json.dumps(doc).encode())
    assert not catalog["operations"][0]["supported"]
    with pytest.raises(ValueError):
        compile_plan(plan(doc))


@pytest.mark.parametrize(
    "raw",
    [
        b'{"openapi":',
        b"a: &x [*x]",
        b"openapi: 3.1.0\nopenapi: 3.0.0",
        b"!!python/object:builtins.object {}",
    ],
)
def test_invalid_and_unsafe_documents(raw):
    with pytest.raises(ValueError):
        parse_document("a.yaml", raw)


def test_target_authorization_and_explicit_selection():
    p = plan()
    p.base_url = "https://untrusted.invalid"
    with pytest.raises(ValueError, match="白名单"):
        compile_plan(p)
    p.base_url = "http://localhost"
    p.selected_operations = []
    with pytest.raises(ValueError, match="选择"):
        compile_plan(p)


def test_credentials_preview_does_not_change_execution_input():
    p = plan(headers={"Authorization": "Bearer synthetic-private-token"})
    from req2test.security.redaction import redact_sensitive

    config = compile_plan(p)
    assert config.api_specs[0].headers["Authorization"] == "Bearer synthetic-private-token"
    assert "synthetic-private-token" not in json.dumps(redact_sensitive(config.model_dump()))


@pytest.mark.parametrize("version", ["3.0.3", "3.1.1"])
def test_versions_and_pointer_escaping(version):
    doc = document()
    doc["openapi"] = version
    doc["components"]["schemas"]["a/b~c"] = doc["components"]["schemas"].pop("Product")
    for response in [
        doc["paths"]["/products"]["post"]["requestBody"],
        doc["paths"]["/products"]["post"]["responses"]["201"],
    ]:
        response["content"]["application/json"]["schema"]["$ref"] = "#/components/schemas/a~1b~0c"
    assert compile_plan(plan(doc)).api_specs[0].json_body["name"] == "demo"


@pytest.mark.parametrize(
    "change",
    ["unknown_operation", "too_many_cases", "invalid_override", "missing_response", "invalid_file"],
)
def test_invalid_plans_are_explicit_errors(change):
    doc = document()
    p = plan(doc)
    if change == "unknown_operation":
        p.selected_operations = ["GET /absent"]
    if change == "too_many_cases":
        doc["paths"]["/products"]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ] = {
            "type": "object",
            "required": [str(i) for i in range(22)],
            "properties": {str(i): {"type": "string"} for i in range(22)},
        }
        p = plan(doc)
    if change == "invalid_override":
        p.overrides = {"POST /products": {"json_body": {"name": 1}}}
    if change == "missing_response":
        p.overrides = {"POST /products": {"expected_status": 202}}
    if change == "invalid_file":
        p.content_base64 = "invalid base64!!"
    with pytest.raises(ValueError):
        compile_plan(p)


def test_no_implicit_validation_status():
    doc = document()
    doc["paths"]["/products"]["post"]["responses"].pop("422")
    assert len(compile_plan(plan(doc)).api_specs) == 1


def test_no_network_during_import_or_compile(monkeypatch):
    import socket

    monkeypatch.setattr(socket.socket, "connect", lambda *_: pytest.fail("unexpected network"))
    assert len(compile_plan(plan()).api_specs) == 4


def test_document_size_and_depth_limits():
    with pytest.raises(ValueError, match="1 MiB"):
        parse_document("a.json", b" " * (1024 * 1024 + 1))
    with pytest.raises(ValueError):
        parse_document("a.json", b"[" * 1000 + b"]" * 1000)


def test_array_nullable_and_enum_payloads():
    doc = document()
    schema = {
        "type": "array",
        "minItems": 1,
        "items": {
            "type": "object",
            "required": ["value", "optional"],
            "properties": {
                "value": {"type": "string", "enum": ["A", "B"]},
                "optional": {"type": "null"},
            },
        },
    }
    doc["paths"]["/products"]["post"]["requestBody"]["content"]["application/json"]["schema"] = (
        schema
    )
    config = compile_plan(plan(doc))
    assert config.api_specs[0].json_body == [{"value": "A", "optional": None}]


def test_openapi_30_exclusive_boundary():
    doc = document()
    doc["openapi"] = "3.0.3"
    doc["components"]["schemas"]["Product"]["properties"]["count"] = {
        "type": "integer",
        "minimum": 0,
        "exclusiveMinimum": True,
    }
    assert compile_plan(plan(doc)).api_specs[0].json_body["count"] > 0


def test_declared_400_negative_cases():
    doc = document()
    responses = doc["paths"]["/products"]["post"]["responses"]
    responses["400"] = responses.pop("422")
    assert all(spec.expected_status == 400 for spec in compile_plan(plan(doc)).api_specs[1:])


@pytest.mark.parametrize(
    "raw", [b"openapi: 3.1.0\npaths: {}\nx: .nan", b"openapi: 3.1.0\npaths: {}\nx: .inf"]
)
def test_yaml_nonfinite_numbers_rejected(raw):
    with pytest.raises(ValueError):
        parse_document("a.yaml", raw)


@pytest.mark.parametrize(
    "override",
    [
        {"expected_status": "UNLABELED_SYNTHETIC_SECRET"},
        {"headers": ["UNLABELED_SYNTHETIC_SECRET"]},
    ],
)
def test_invalid_overrides_do_not_echo_raw_values(override):
    p = plan()
    p.overrides = {"POST /products": override}
    with pytest.raises(ValueError) as exc:
        compile_plan(p)
    assert "UNLABELED_SYNTHETIC_SECRET" not in str(exc.value)
