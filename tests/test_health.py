from fastapi.testclient import TestClient

from app.main import create_app


def test_health_check_returns_ok(tmp_path):
    app = create_app(database_path=tmp_path / "test.sqlite3", start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
