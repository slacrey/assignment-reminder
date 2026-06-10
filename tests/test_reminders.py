from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.database import connect
from app.main import create_app
from app.reminders import process_due_reminders


def make_app(tmp_path):
    return create_app(database_path=tmp_path / "test.sqlite3", start_scheduler=False)


def create_due_assignment(client):
    child = client.post("/api/children", json={"name": "小明", "qq_number": "123456"}).json()
    future = (datetime.now() + timedelta(hours=1)).replace(microsecond=0).isoformat()
    assignment = client.post(
        "/api/assignments",
        json={
            "child_id": child["id"],
            "title": "数学练习",
            "description": "完成第 10 页",
            "remind_at": future,
        },
    ).json()
    return assignment


def force_assignment_due(database_path, assignment_id):
    due_at = (datetime.now() - timedelta(minutes=1)).replace(microsecond=0).isoformat()
    with connect(database_path) as connection:
        connection.execute(
            "UPDATE assignments SET remind_at = ? WHERE id = ?",
            (due_at, assignment_id),
        )
        connection.commit()


def test_process_due_reminders_marks_assignment_and_writes_log(tmp_path):
    app = make_app(tmp_path)

    with TestClient(app) as client:
        assignment = create_due_assignment(client)
        force_assignment_due(app.state.database_path, assignment["id"])

        processed = process_due_reminders(app.state.database_path)
        logs = client.get("/api/reminder-logs").json()
        assignments = client.get("/api/assignments").json()

    assert processed == 1
    assert assignments[0]["status"] == "reminded"
    assert logs[0]["target_qq"] == "123456"
    assert "数学练习" in logs[0]["message"]


def test_process_due_reminders_does_not_repeat(tmp_path):
    app = make_app(tmp_path)

    with TestClient(app) as client:
        assignment = create_due_assignment(client)
        force_assignment_due(app.state.database_path, assignment["id"])

        assert process_due_reminders(app.state.database_path) == 1
        assert process_due_reminders(app.state.database_path) == 0
        logs = client.get("/api/reminder-logs").json()

    assert len(logs) == 1
