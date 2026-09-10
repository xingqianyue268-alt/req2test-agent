from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

import req2test.api as api_module
from req2test import evaluation_api
from req2test.db.models import EvaluationRunORM
from req2test.db.repositories import users
from req2test.db.session import get_db
from req2test.security.passwords import hash_password
from req2test.services.evaluation_service import EvaluationDatasetRegistry, EvaluationService

PASSWORD = "correct horse battery staple"


def _client(db_session, monkeypatch):
    def override_db():
        yield db_session

    published: list[list] = []

    def publisher(args, _eager):
        published.append(args)
        return args[0]

    service = EvaluationService(publisher, registry=EvaluationDatasetRegistry("evals"))
    api_module.app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(evaluation_api, "evaluation_service", service)
    return TestClient(api_module.app), published


def _user(db_session, email, role="user"):
    record = users.create_user(
        db_session, email=email, password_hash=hash_password(PASSWORD), role=role
    )
    db_session.commit()
    return record


def _login(client, email):
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200


def _configuration(prompt="workflow-v1", *, api_key=""):
    return {
        "llm_settings": {
            "mode": "demo",
            "model": "demo-eval",
            "api_key": api_key,
            "temperature": 0.1,
            "seed": 7,
        },
        "generation_config": {"prompt_version": prompt},
    }


def test_evaluation_api_dataset_run_detail_and_secret_boundary(db_session, monkeypatch):
    client, published = _client(db_session, monkeypatch)
    owner = _user(db_session, "eval-owner@example.com")
    other = _user(db_session, "eval-other@example.com")
    try:
        assert client.get("/api/v1/evaluations/datasets").status_code == 401
        assert client.get("/evaluations", follow_redirects=False).status_code == 307

        _login(client, owner.email)
        page = client.get("/evaluations")
        assert page.status_code == 200
        assert "AI Evaluation Center" in page.text
        assert "latency_ms" in page.text
        assert "revision_iterations" in page.text

        datasets = client.get("/api/v1/evaluations/datasets").json()
        assert datasets["items"][0]["name"] == "golden_demo"
        assert len(datasets["items"][0]["digest"]) == 64

        created = client.post(
            "/api/v1/evaluations/runs",
            json={
                "dataset_name": "golden_demo",
                "configuration": _configuration(api_key="never-persist-this"),
            },
        )
        assert created.status_code == 202
        run_id = created.json()["run"]["id"]
        assert "never-persist-this" not in created.text
        assert len(published) == 1
        assert published[0][0] == run_id
        stored = db_session.scalar(select(EvaluationRunORM).where(EvaluationRunORM.id == run_id))
        assert "never-persist-this" not in str(stored.generation_config)
        assert "never-persist-this" not in str(stored.judge_config)

        detail = client.get(f"/api/v1/evaluations/runs/{run_id}")
        assert detail.status_code == 200
        assert detail.json()["seed"] == 7
        assert "api_key" not in detail.text

        client.post("/api/v1/auth/logout")
        _login(client, other.email)
        assert client.get(f"/api/v1/evaluations/runs/{run_id}").status_code == 404
        run_list = client.get("/api/v1/evaluations/runs").json()
        assert run_id not in {item["id"] for item in run_list["items"]}
    finally:
        api_module.app.dependency_overrides.clear()


def test_evaluation_api_ab_comparison_and_dataset_path_rejection(db_session, monkeypatch):
    client, published = _client(db_session, monkeypatch)
    owner = _user(db_session, "eval-ab@example.com")
    other = _user(db_session, "eval-ab-other@example.com")
    try:
        _login(client, owner.email)
        rejected = client.post(
            "/api/v1/evaluations/runs",
            json={"dataset_name": "../golden_demo", "configuration": _configuration()},
        )
        assert rejected.status_code == 404

        created = client.post(
            "/api/v1/evaluations/comparisons",
            json={
                "name": "Prompt A/B",
                "dataset_name": "golden_demo",
                "configuration_a": _configuration("workflow-v1"),
                "configuration_b": _configuration("workflow-grounded-v2"),
            },
        )
        assert created.status_code == 202
        comparison_id = created.json()["comparison"]["id"]
        assert len(published) == 2

        detail = client.get(f"/api/v1/evaluations/comparisons/{comparison_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["configuration_a"]["configuration_label"] == "A"
        assert body["configuration_b"]["configuration_label"] == "B"
        assert body["configuration_a"]["dataset_digest"] == body["dataset_digest"]

        client.post("/api/v1/auth/logout")
        _login(client, other.email)
        assert (
            client.get(f"/api/v1/evaluations/comparisons/{comparison_id}").status_code
            == 404
        )
        comparison_list = client.get("/api/v1/evaluations/comparisons").json()
        assert comparison_id not in {
            item["id"] for item in comparison_list["items"]
        }
    finally:
        api_module.app.dependency_overrides.clear()


def test_admin_lists_and_reads_other_users_runs_and_comparisons(db_session, monkeypatch):
    client, _published = _client(db_session, monkeypatch)
    owner = _user(db_session, "eval-resource-owner@example.com")
    admin = _user(db_session, "eval-admin@example.com", role="admin")
    try:
        _login(client, owner.email)
        run = client.post(
            "/api/v1/evaluations/runs",
            json={"dataset_name": "golden_demo", "configuration": _configuration()},
        ).json()["run"]
        comparison = client.post(
            "/api/v1/evaluations/comparisons",
            json={
                "name": "Owner experiment",
                "dataset_name": "golden_demo",
                "configuration_a": _configuration("workflow-v1"),
                "configuration_b": _configuration("workflow-grounded-v2"),
            },
        ).json()["comparison"]
        client.post("/api/v1/auth/logout")

        _login(client, admin.email)
        run_list = client.get("/api/v1/evaluations/runs").json()
        comparison_list = client.get("/api/v1/evaluations/comparisons").json()
        assert run["id"] in {item["id"] for item in run_list["items"]}
        assert comparison["id"] in {item["id"] for item in comparison_list["items"]}
        assert client.get(f"/api/v1/evaluations/runs/{run['id']}").status_code == 200
        assert (
            client.get(f"/api/v1/evaluations/comparisons/{comparison['id']}").status_code
            == 200
        )
    finally:
        api_module.app.dependency_overrides.clear()
