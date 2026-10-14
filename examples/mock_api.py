"""Local-only synthetic API: uvicorn examples.mock_api:app --host 127.0.0.1 --port 8081.

No external systems, database or real credentials. Creates are deterministic for
repeatability across both executors; this is a testing fixture, not production auth.
"""

from fastapi import FastAPI, Header, HTTPException, Query
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
