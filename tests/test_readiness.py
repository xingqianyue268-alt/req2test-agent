from fastapi.testclient import TestClient

import req2test.api as api_module


client = TestClient(api_module.app)


def test_health_is_liveness_even_when_database_is_down(monkeypatch):
    monkeypatch.setattr(api_module, "database_is_ready", lambda: False)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_503_when_database_is_down(monkeypatch):
    monkeypatch.setattr(api_module, "database_is_ready", lambda: False)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["checks"]["database"] == "down"


def test_ready_returns_200_when_database_is_available(monkeypatch):
    monkeypatch.setattr(api_module, "database_is_ready", lambda: True)
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ready"}}
