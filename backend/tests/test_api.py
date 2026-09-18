from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_available():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/projects" in response.json()["paths"]
