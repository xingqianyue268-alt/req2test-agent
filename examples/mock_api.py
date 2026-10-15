"""Local-only synthetic API: uvicorn examples.mock_api:app --host 127.0.0.1 --port 8081.

No external systems, database or real credentials. Creates are deterministic for
repeatability across both executors; this is a testing fixture, not production auth.
"""

import asyncio
import time
import uuid
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="Req2Test Synthetic Shop", version="1.0")


class Login(BaseModel):
    username: str = Field(min_length=1, examples=["demo"])
    password: str = Field(min_length=1, examples=["demo"])


class LoginResponse(BaseModel):
    access_token: str
    token_type: str


class User(BaseModel):
    id: int
    name: str


class Metadata(BaseModel):
    active: bool
    tags: list[str]


class Product(BaseModel):
    model_config = ConfigDict(strict=True)
    name: str = Field(min_length=1)
    price: int = Field(ge=1)
    metadata: Metadata


@app.post("/login", response_model=LoginResponse)
def login(body: Login):
    if body.username != "demo" or body.password != "demo":
        raise HTTPException(status_code=401, detail="synthetic credentials required")
    return {"access_token": "synthetic-demo-token", "token_type": "bearer"}


@app.get(
    "/users/{user_id}",
    response_model=User,
    responses={401: {"description": "authentication required"}},
)
def user(user_id: int, authorization: str = Header(default="")):
    if authorization != "Bearer synthetic-demo-token":
        raise HTTPException(status_code=401, detail="synthetic token required")
    return {"id": user_id, "name": "demo"}


@app.get("/products", response_model=list[Product])
def products(limit: int = Query(default=1, ge=1, le=5)):
    return [{"name": "demo", "price": 1, "metadata": {"active": True, "tags": ["demo"]}}][:limit]


@app.post("/products", status_code=201, response_model=Product)
def create_product(body: Product):
    return body


@app.post("/validate", response_model=Product)
def validate(body: Product, quantity: int = Query(ge=1)):
    return body


# P1-B disposable state is separate from the P1-A deterministic endpoints.
# Preparation is explicit; expired/deleted run IDs are never auto-created by writes.
_RUNS = {}


def _active(run_id):
    run = _RUNS.get(run_id)
    if not run or run["expires"] < time.monotonic():
        _RUNS.pop(run_id, None)
        raise HTTPException(status_code=404, detail="isolated run does not exist")
    return run


@app.get("/__req2test__/capabilities")
def mock_capabilities():
    return {"protocol": "req2test-disposable-v1"}


@app.put("/__req2test__/runs/{run_id}", status_code=201)
def prepare_run(run_id: str, body: dict):
    try:
        assert uuid.UUID(hex=run_id).hex == run_id
    except (ValueError, AssertionError):
        raise HTTPException(status_code=422, detail="invalid run id") from None
    for key in list(_RUNS):
        if _RUNS[key]["expires"] < time.monotonic():
            _RUNS.pop(key)
    if run_id in _RUNS:
        raise HTTPException(status_code=409, detail="run already exists")
    try:
        seed = [Product.model_validate(item).model_dump() for item in body.get("products", [])]
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="invalid synthetic seed") from None
    _RUNS[run_id] = {
        "products": {item["name"]: item for item in seed},
        "expires": time.monotonic() + 600,
        "writes": 0,
    }
    return {"run_id": run_id}


@app.delete("/__req2test__/runs/{run_id}", status_code=204)
def cleanup_run(run_id: str):
    _RUNS.pop(run_id, None)
    return Response(status_code=204)


@app.get("/isolated/products")
def isolated_products(x_req2test_run: Annotated[str, Header()]):
    run = _active(x_req2test_run)
    return {"items": list(run["products"].values()), "writes": run["writes"]}


@app.post("/isolated/products", status_code=201)
async def isolated_create(
    body: Product,
    x_req2test_run: Annotated[str, Header()],
    delay: float = Query(default=0, ge=0, le=2),
):
    if delay:
        await asyncio.sleep(delay)
    run = _active(x_req2test_run)  # Re-check after delay: cleanup prevents late timed-out writes.
    if body.name in run["products"]:
        raise HTTPException(status_code=409, detail="product already exists in this run")
    run["products"][body.name] = body.model_dump()
    run["writes"] += 1
    return {"product": body.model_dump(), "writes": run["writes"]}


@app.put("/isolated/products/{name}")
def isolated_update(name: str, body: Product, x_req2test_run: Annotated[str, Header()]):
    run = _active(x_req2test_run)
    if name not in run["products"]:
        raise HTTPException(status_code=404, detail="missing product")
    run["products"][name] = body.model_dump()
    run["writes"] += 1
    return {"product": body.model_dump(), "writes": run["writes"]}


@app.delete("/isolated/products/{name}", status_code=204)
def isolated_delete(name: str, x_req2test_run: Annotated[str, Header()]):
    run = _active(x_req2test_run)
    if name not in run["products"]:
        raise HTTPException(status_code=404, detail="missing product")
    del run["products"][name]
    run["writes"] += 1
    return Response(status_code=204)
