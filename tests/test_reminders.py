import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

import app.reminders as reminders
from app.database import connect
from app.main import create_app
from app.qq_sender import SendMessageResult
from app.reminders import process_due_reminders


class FakeSender:
    provider = "fake"

    def __init__(self, result):
        self.result = result
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        return self.result


class StatusObservingSender:
    provider = "fake"

    def __init__(self, database_path, assignment_id):
        self.database_path = database_path
        self.assignment_id = assignment_id
        self.status_seen = None
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        with connect(self.database_path) as connection:
            self.status_seen = connection.execute(
                "SELECT status FROM assignments WHERE id = ?",
                (self.assignment_id,),
            ).fetchone()["status"]
        return SendMessageResult(provider="onebot", success=True, provider_message_id="abc-123")


class RaisingSender:
    provider = "onebot"

    def __init__(self):
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        raise RuntimeError("OneBot exploded")


REMINDER_LOG_KEYS = {
    "id",
    "assignment_id",
    "child_id",
    "child_name",
    "target_qq",
    "assignment_title",
    "message",
    "scheduled_at",
    "sent_at",
    "provider",
    "provider_message_id",
    "status",
    "error_message",
    "created_at",
}


def make_app(tmp_path):
    return create_app(database_path=tmp_path / "test.sqlite3", start_scheduler=False)


def create_due_assignment(client, title="数学练习", description="完成第 10 页"):
    child = client.post("/api/children", json={"name": "小明", "qq_number": "123456"}).json()
    future = (datetime.now() + timedelta(hours=1)).replace(microsecond=0).isoformat()
    assignment = client.post(
        "/api/assignments",
        json={
            "child_id": child["id"],
            "title": title,
            "description": description,
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


def force_assignment_sending(database_path, assignment_id, updated_at):
    with connect(database_path) as connection:
        connection.execute(
            "UPDATE assignments SET status = 'sending', updated_at = ? WHERE id = ?",
            (updated_at, assignment_id),
        )
        connection.commit()


def assignment_statuses(database_path):
    with connect(database_path) as connection:
        return [
            row["status"]
            for row in connection.execute("SELECT status FROM assignments ORDER BY id").fetchall()
        ]


def test_build_message_omits_empty_description():
    message = reminders.build_message("小明", "数学练习", "")

    assert message == "小明，现在该写数学练习了。"


def test_build_message_includes_description_inline():
    message = reminders.build_message("陈琦榕", "数学作业", "感觉做")

    assert message == "陈琦榕，现在该写数学作业了，感觉做。"


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
    assert assignments[0]["updated_at"].endswith("+00:00")
    assert set(logs[0]) == REMINDER_LOG_KEYS
    assert logs[0]["child_name"] == "小明"
    assert logs[0]["target_qq"] == "123456"
    assert logs[0]["assignment_title"] == "数学练习"
    assert logs[0]["status"] == "success"
    assert logs[0]["provider"] == "simulated"
    assert logs[0]["provider_message_id"] is None
    assert logs[0]["error_message"] is None
    assert logs[0]["sent_at"].endswith("+00:00")
    assert "数学练习" in logs[0]["message"]


def test_process_due_reminders_uses_configured_sender(tmp_path):
    app = make_app(tmp_path)
    sender = FakeSender(
        SendMessageResult(
            provider="onebot",
            success=True,
            provider_message_id="abc-123",
        )
    )

    with TestClient(app) as client:
        assignment = create_due_assignment(client)
        force_assignment_due(app.state.database_path, assignment["id"])

        processed = process_due_reminders(app.state.database_path, sender=sender)
        logs = client.get("/api/reminder-logs").json()
        assignments = client.get("/api/assignments").json()

    assert processed == 1
    assert assignments[0]["status"] == "reminded"
    assert sender.requests[0].target_qq == "123456"
    assert "数学练习" in sender.requests[0].message
    assert logs[0]["provider"] == "onebot"
    assert logs[0]["provider_message_id"] == "abc-123"


def test_process_due_reminders_claims_assignment_before_sending(tmp_path):
    app = make_app(tmp_path)

    with TestClient(app) as client:
        assignment = create_due_assignment(client)
        force_assignment_due(app.state.database_path, assignment["id"])
        sender = StatusObservingSender(app.state.database_path, assignment["id"])

        processed = process_due_reminders(app.state.database_path, sender=sender)
        assignments = client.get("/api/assignments").json()

    assert processed == 1
    assert sender.status_seen == "sending"
    assert assignments[0]["status"] == "reminded"


def test_process_due_reminders_does_not_send_stale_claimed_assignment(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    sender = FakeSender(SendMessageResult(provider="onebot", success=True))

    with TestClient(app) as client:
        assignment = create_due_assignment(client)
        force_assignment_due(app.state.database_path, assignment["id"])
        stale_rows = reminders._due_assignments(
            app.state.database_path,
            reminders._local_now_iso(),
        )
        with connect(app.state.database_path) as connection:
            connection.execute(
                "UPDATE assignments SET status = 'cancelled' WHERE id = ?",
                (assignment["id"],),
            )

        monkeypatch.setattr(reminders, "_due_assignments", lambda database_path, now_iso: stale_rows)

        processed = process_due_reminders(app.state.database_path, sender=sender)
        logs = client.get("/api/reminder-logs").json()
        assignments = client.get("/api/assignments").json()

    assert processed == 0
    assert sender.requests == []
    assert logs == []
    assert assignments[0]["status"] == "cancelled"


def test_process_due_reminders_recovers_stale_sending_assignment(tmp_path):
    app = make_app(tmp_path)
    sender = FakeSender(
        SendMessageResult(
            provider="onebot",
            success=True,
            provider_message_id="abc-123",
        )
    )
    old_updated_at = (
        datetime.now(UTC) - timedelta(minutes=10)
    ).replace(microsecond=0).isoformat()

    with TestClient(app) as client:
        assignment = create_due_assignment(client)
        force_assignment_due(app.state.database_path, assignment["id"])
        force_assignment_sending(app.state.database_path, assignment["id"], old_updated_at)

        processed = process_due_reminders(app.state.database_path, sender=sender)
        logs = client.get("/api/reminder-logs").json()
        assignments = client.get("/api/assignments").json()

    assert processed == 1
    assert len(sender.requests) == 1
    assert assignments[0]["status"] == "reminded"
    assert logs[0]["status"] == "success"
    assert logs[0]["provider_message_id"] == "abc-123"


def test_process_due_reminders_does_not_recover_fresh_sending_assignment(tmp_path):
    app = make_app(tmp_path)
    sender = FakeSender(SendMessageResult(provider="onebot", success=True))
    fresh_updated_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    with TestClient(app) as client:
        assignment = create_due_assignment(client)
        force_assignment_due(app.state.database_path, assignment["id"])
        force_assignment_sending(app.state.database_path, assignment["id"], fresh_updated_at)

        processed = process_due_reminders(app.state.database_path, sender=sender)
        logs = client.get("/api/reminder-logs").json()
        assignments = client.get("/api/assignments").json()

    assert processed == 0
    assert sender.requests == []
    assert logs == []
    assert assignments[0]["status"] == "sending"


def test_process_due_reminders_keeps_assignment_pending_when_sender_fails(tmp_path):
    app = make_app(tmp_path)
    sender = FakeSender(
        SendMessageResult(
            provider="onebot",
            success=False,
            error_message="OneBot request failed",
        )
    )

    with TestClient(app) as client:
        assignment = create_due_assignment(client)
        force_assignment_due(app.state.database_path, assignment["id"])

        processed = process_due_reminders(app.state.database_path, sender=sender)
        logs = client.get("/api/reminder-logs").json()
        assignments = client.get("/api/assignments").json()

    assert processed == 0
    assert assignments[0]["status"] == "pending"
    assert logs[0]["status"] == "failed"
    assert logs[0]["provider"] == "onebot"
    assert logs[0]["error_message"] == "OneBot request failed"
    assert "sending" not in assignment_statuses(app.state.database_path)


def test_process_due_reminders_restores_pending_when_sender_raises(tmp_path):
    app = make_app(tmp_path)
    sender = RaisingSender()

    with TestClient(app) as client:
        assignment = create_due_assignment(client)
        force_assignment_due(app.state.database_path, assignment["id"])

        processed = process_due_reminders(app.state.database_path, sender=sender)
        logs = client.get("/api/reminder-logs").json()
        assignments = client.get("/api/assignments").json()

    assert processed == 0
    assert assignments[0]["status"] == "pending"
    assert logs[0]["status"] == "failed"
    assert logs[0]["provider"] == "onebot"
    assert logs[0]["error_message"] == "OneBot exploded"
    assert "sending" not in assignment_statuses(app.state.database_path)


def test_process_due_reminders_does_not_repeat(tmp_path):
    app = make_app(tmp_path)

    with TestClient(app) as client:
        assignment = create_due_assignment(client)
        force_assignment_due(app.state.database_path, assignment["id"])

        assert process_due_reminders(app.state.database_path) == 1
        assert process_due_reminders(app.state.database_path) == 0
        logs = client.get("/api/reminder-logs").json()

    assert len(logs) == 1


def test_process_due_reminders_records_failure_and_continues(tmp_path, monkeypatch):
    app = make_app(tmp_path)

    with TestClient(app) as client:
        failing_assignment = create_due_assignment(client, title="数学练习")
        succeeding_assignment = create_due_assignment(client, title="语文阅读")
        force_assignment_due(app.state.database_path, failing_assignment["id"])
        force_assignment_due(app.state.database_path, succeeding_assignment["id"])

        original_build_message = reminders.build_message

        def flaky_build_message(child_name, title, description):
            if title == "数学练习":
                raise RuntimeError("message failed")
            return original_build_message(child_name, title, description)

        monkeypatch.setattr(reminders, "build_message", flaky_build_message)

        processed = process_due_reminders(app.state.database_path)
        logs = client.get("/api/reminder-logs").json()
        assignments = client.get("/api/assignments").json()

    assert processed == 1
    log_statuses = {log["assignment_title"]: log["status"] for log in logs}
    assert log_statuses == {"语文阅读": "success", "数学练习": "failed"}
    failed_log = next(log for log in logs if log["assignment_title"] == "数学练习")
    assert failed_log["error_message"] == "message failed"
    assignment_statuses = {assignment["title"]: assignment["status"] for assignment in assignments}
    assert assignment_statuses == {"数学练习": "pending", "语文阅读": "reminded"}


def test_run_reminder_loop_continues_after_scan_error(tmp_path, monkeypatch):
    async def exercise_loop():
        calls = 0
        second_call = asyncio.Event()

        def flaky_process_due_reminders(database_path, sender=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("scan failed")
            second_call.set()
            return 0

        monkeypatch.setattr(reminders, "process_due_reminders", flaky_process_due_reminders)

        task = asyncio.create_task(
            reminders.run_reminder_loop(tmp_path / "test.sqlite3", interval_seconds=0.01)
        )
        try:
            await asyncio.wait_for(second_call.wait(), timeout=1)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        assert calls >= 2

    asyncio.run(exercise_loop())
