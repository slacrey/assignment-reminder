from fastapi.testclient import TestClient

from app.database import connect
from app.main import create_app
from app.reminders import process_due_reminders


CHILD_KEYS = {
    "id",
    "name",
    "qq_number",
    "assignment_count",
    "last_reminded_at",
    "created_at",
    "updated_at",
}


def make_client(tmp_path):
    app = create_app(database_path=tmp_path / "test.sqlite3", start_scheduler=False)
    return TestClient(app)


def test_create_child(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/children",
            json={"name": " 小明 ", "qq_number": " 123456 "},
        )

    assert response.status_code == 201
    assert set(response.json()) == CHILD_KEYS
    assert response.json()["name"] == "小明"
    assert response.json()["qq_number"] == "123456"
    assert response.json()["assignment_count"] == 0
    assert response.json()["last_reminded_at"] is None


def test_create_child_rejects_invalid_qq(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/children",
            json={"name": "小明", "qq_number": "abc"},
        )

    assert response.status_code == 422


def test_create_child_rejects_unknown_fields(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/children",
            json={"name": "小明", "qq_number": "123456", "nickname": "明明"},
        )

    assert response.status_code == 422


def test_list_children_includes_assignment_count(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/api/children",
            json={"name": "小明", "qq_number": "123456"},
        )
        response = client.get("/api/children")

    assert response.status_code == 200
    assert set(response.json()[0]) == CHILD_KEYS
    assert response.json()[0]["assignment_count"] == 0
    assert response.json()[0]["last_reminded_at"] is None


def test_update_child(tmp_path):
    with make_client(tmp_path) as client:
        create_response = client.post(
            "/api/children",
            json={"name": "小明", "qq_number": "123456"},
        )
        child_id = create_response.json()["id"]

        response = client.patch(
            f"/api/children/{child_id}",
            json={"name": "小红", "qq_number": "654321"},
        )

    assert response.status_code == 200
    assert set(response.json()) == CHILD_KEYS
    assert response.json()["name"] == "小红"
    assert response.json()["qq_number"] == "654321"


def test_update_child_rejects_unknown_fields(tmp_path):
    with make_client(tmp_path) as client:
        create_response = client.post(
            "/api/children",
            json={"name": "小明", "qq_number": "123456"},
        )
        child_id = create_response.json()["id"]

        response = client.patch(
            f"/api/children/{child_id}",
            json={"qq_numbr": "654321"},
        )

    assert response.status_code == 422


def test_update_child_returns_not_found(tmp_path):
    with make_client(tmp_path) as client:
        response = client.patch(
            "/api/children/999",
            json={"name": "小红"},
        )

    assert response.status_code == 404


def test_delete_child_removes_related_assignments_and_reminder_logs(tmp_path):
    with make_client(tmp_path) as client:
        child = client.post(
            "/api/children",
            json={"name": "小明", "qq_number": "123456"},
        ).json()
        assignment_response = client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": "数学作业",
                "description": "做第一页",
                "remind_at": "2099-06-14T18:00:00",
            },
        )
        assignment = assignment_response.json()
        with connect(client.app.state.database_path) as connection:
            connection.execute(
                "UPDATE assignments SET remind_at = ? WHERE id = ?",
                ("2026-06-14T18:00:00", assignment["id"]),
            )

        process_due_reminders(client.app.state.database_path)

        response = client.delete(f"/api/children/{child['id']}")

        assert response.status_code == 204
        assert client.get("/api/children").json() == []
        assert client.get("/api/assignments").json() == []
        assert client.get("/api/reminder-logs").json() == []


def test_delete_child_returns_not_found(tmp_path):
    with make_client(tmp_path) as client:
        response = client.delete("/api/children/999")

    assert response.status_code == 404
