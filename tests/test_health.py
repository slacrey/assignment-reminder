from fastapi.testclient import TestClient

from app.database import connect
from app.main import create_app


def test_health_check_returns_ok(tmp_path):
    app = create_app(database_path=tmp_path / "test.sqlite3", start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_startup_initializes_database(tmp_path):
    database_path = tmp_path / "test.sqlite3"
    app = create_app(database_path=database_path, start_scheduler=False)

    with TestClient(app):
        pass

    with connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

    assert [row["name"] for row in rows] == ["assignments", "children", "reminder_logs"]
