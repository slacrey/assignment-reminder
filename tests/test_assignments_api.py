from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.database import connect
from app.main import create_app


def make_client(tmp_path):
    app = create_app(database_path=tmp_path / "test.sqlite3", start_scheduler=False)
    return TestClient(app)


def create_child(client):
    return client.post("/api/children", json={"name": "小明", "qq_number": "123456"}).json()


def future_time():
    return (datetime.now() + timedelta(hours=1)).replace(microsecond=0).isoformat()


def past_time():
    return (datetime.now() - timedelta(hours=1)).replace(microsecond=0).isoformat()


def test_create_assignment(tmp_path):
    with make_client(tmp_path) as client:
        child = create_child(client)
        response = client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": "数学练习",
                "description": "完成第 10 页",
                "remind_at": future_time(),
            },
        )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["title"] == "数学练习"


def test_create_assignment_trims_title(tmp_path):
    with make_client(tmp_path) as client:
        child = create_child(client)
        response = client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": " 数学练习 ",
                "description": "",
                "remind_at": future_time(),
            },
        )

    assert response.status_code == 201
    assert response.json()["title"] == "数学练习"


def test_create_assignment_defaults_missing_description(tmp_path):
    with make_client(tmp_path) as client:
        child = create_child(client)
        response = client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": "数学练习",
                "remind_at": future_time(),
            },
        )

    assert response.status_code == 201
    assert response.json()["description"] == ""


def test_create_assignment_rejects_missing_child(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/assignments",
            json={
                "child_id": 999,
                "title": "数学练习",
                "description": "",
                "remind_at": future_time(),
            },
        )

    assert response.status_code == 404


def test_create_assignment_rejects_empty_title(tmp_path):
    with make_client(tmp_path) as client:
        child = create_child(client)
        response = client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": " ",
                "description": "",
                "remind_at": future_time(),
            },
        )

    assert response.status_code == 422


def test_create_assignment_rejects_past_reminder_time(tmp_path):
    with make_client(tmp_path) as client:
        child = create_child(client)
        response = client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": "数学练习",
                "description": "",
                "remind_at": past_time(),
            },
        )

    assert response.status_code == 422


def test_create_assignment_rejects_date_without_time(tmp_path):
    with make_client(tmp_path) as client:
        child = create_child(client)
        response = client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": "数学练习",
                "description": "",
                "remind_at": "2026-06-11",
            },
        )

    assert response.status_code == 422


def test_create_assignment_rejects_timezone_offset(tmp_path):
    with make_client(tmp_path) as client:
        child = create_child(client)
        response = client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": "数学练习",
                "description": "",
                "remind_at": f"{future_time()}+08:00",
            },
        )

    assert response.status_code == 422


def test_create_assignment_rejects_unknown_fields(tmp_path):
    with make_client(tmp_path) as client:
        child = create_child(client)
        response = client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": "数学练习",
                "description": "",
                "remind_at": future_time(),
                "priority": "high",
            },
        )

    assert response.status_code == 422


def test_list_assignments_includes_child_fields_ordered_by_remind_at(tmp_path):
    with make_client(tmp_path) as client:
        child = create_child(client)
        later = (datetime.now() + timedelta(hours=2)).replace(microsecond=0).isoformat()
        sooner = (datetime.now() + timedelta(minutes=30)).replace(microsecond=0).isoformat()
        client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": "数学练习",
                "description": "",
                "remind_at": later,
            },
        )
        client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": "语文阅读",
                "description": "",
                "remind_at": sooner,
            },
        )

        response = client.get("/api/assignments")

    assert response.status_code == 200
    assert [assignment["title"] for assignment in response.json()] == ["语文阅读", "数学练习"]
    assert response.json()[0]["child_name"] == "小明"
    assert response.json()[0]["child_qq_number"] == "123456"


def test_cancel_pending_assignment(tmp_path):
    with make_client(tmp_path) as client:
        child = create_child(client)
        create_response = client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": "数学练习",
                "description": "",
                "remind_at": future_time(),
            },
        )
        assert create_response.status_code == 201
        assignment = create_response.json()
        response = client.patch(f"/api/assignments/{assignment['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_rejects_non_pending_assignment(tmp_path):
    with make_client(tmp_path) as client:
        child = create_child(client)
        create_response = client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": "数学练习",
                "description": "",
                "remind_at": future_time(),
            },
        )
        assert create_response.status_code == 201
        assignment = create_response.json()
        client.patch(f"/api/assignments/{assignment['id']}/cancel")

        response = client.patch(f"/api/assignments/{assignment['id']}/cancel")

    assert response.status_code == 409


def test_cancel_missing_assignment_returns_not_found(tmp_path):
    with make_client(tmp_path) as client:
        response = client.patch("/api/assignments/999/cancel")

    assert response.status_code == 404


def test_cancel_does_not_overwrite_assignment_that_stopped_being_pending(tmp_path):
    database_path = tmp_path / "test.sqlite3"
    app = create_app(database_path=database_path, start_scheduler=False)

    with TestClient(app) as client:
        child = create_child(client)
        create_response = client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": "数学练习",
                "description": "",
                "remind_at": future_time(),
            },
        )
        assignment_id = create_response.json()["id"]

        with connect(database_path) as connection:
            connection.execute(
                "UPDATE assignments SET status = 'reminded' WHERE id = ?",
                (assignment_id,),
            )

        response = client.patch(f"/api/assignments/{assignment_id}/cancel")
        assignments = client.get("/api/assignments").json()

    assert response.status_code == 409
    assert assignments[0]["status"] == "reminded"
