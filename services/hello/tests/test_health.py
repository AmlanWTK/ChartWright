"""Tests for the hello service — proves the pytest lane and coverage gate."""

from fastapi.testclient import TestClient

from hello.main import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "hello"
    assert body["version"] == "0.1.0"


def test_readyz_returns_ok() -> None:
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_root_points_to_docs() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "hello service" in resp.json()["message"]
