# Assignment Reminder MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local Web MVP where a parent can add children, create homework reminders, and see simulated QQ reminder logs when reminders become due.

**Architecture:** Implement a single FastAPI service that serves both JSON APIs and static frontend assets. Store data in a local SQLite database through small repository functions, and run a background reminder scanner in the same process. Keep QQ delivery behind a tiny sender function so the MVP uses logs now and can swap in a real QQ adapter later.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic, SQLite via Python `sqlite3`, pytest, HTTPX/TestClient, static HTML/CSS/JavaScript.

---

## Preconditions

- Current approved design: `docs/plans/2026-06-10-assignment-reminder-mvp-design.md`.
- Repository currently has no application code.
- Use local system time for MVP.
- Do not add authentication, real QQ integration, or cloud deployment in this implementation.

## Task 1: Project Skeleton and Health Endpoint

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `tests/test_health.py`

**Step 1: Write the failing test**

Create `tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_check_returns_ok(tmp_path):
    app = create_app(database_path=tmp_path / "test.sqlite3", start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_health.py -v
```

Expected: FAIL because project dependencies and `app.main` do not exist yet.

**Step 3: Add minimal project setup**

Create `pyproject.toml` with dependencies:

```toml
[project]
name = "assignment-reminder"
version = "0.1.0"
description = "Local homework reminder MVP with simulated QQ logs"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
]

[dependency-groups]
dev = [
  "httpx>=0.27.0",
  "pytest>=8.0.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Create `app/main.py`:

```python
from pathlib import Path

from fastapi import FastAPI


def create_app(database_path: str | Path | None = None, start_scheduler: bool = True) -> FastAPI:
    app = FastAPI(title="Assignment Reminder")
    app.state.database_path = Path(database_path) if database_path else Path("data/assignment_reminder.sqlite3")
    app.state.start_scheduler = start_scheduler

    @app.get("/api/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

**Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/test_health.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add pyproject.toml app/__init__.py app/main.py tests/test_health.py
git commit -m "feat: add FastAPI app skeleton"
```

## Task 2: SQLite Schema and Database Helpers

**Files:**
- Create: `app/database.py`
- Create: `tests/test_database.py`
- Modify: `app/main.py`

**Step 1: Write the failing test**

Create `tests/test_database.py`:

```python
import sqlite3

from app.database import connect, init_db


def table_names(database_path):
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
    return [row[0] for row in rows]


def test_init_db_creates_core_tables(tmp_path):
    database_path = tmp_path / "test.sqlite3"

    init_db(database_path)

    assert table_names(database_path) == ["assignments", "children", "reminder_logs"]


def test_connect_returns_dict_like_rows(tmp_path):
    database_path = tmp_path / "test.sqlite3"
    init_db(database_path)

    with connect(database_path) as connection:
        row = connection.execute("SELECT 1 AS value").fetchone()

    assert row["value"] == 1
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_database.py -v
```

Expected: FAIL because `app.database` does not exist.

**Step 3: Implement database helpers**

Create `app/database.py` with:

- `connect(database_path)` that creates the parent directory, opens SQLite, sets `row_factory = sqlite3.Row`, and enables foreign keys.
- `init_db(database_path)` that creates these tables:
  - `children`
  - `assignments`
  - `reminder_logs`
- Indexes:
  - `idx_assignments_status_remind_at`
  - `idx_reminder_logs_created_at`

Schema details:

```sql
CREATE TABLE IF NOT EXISTS children (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  qq_number TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assignments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  child_id INTEGER NOT NULL REFERENCES children(id),
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  remind_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'reminded', 'cancelled')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminder_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assignment_id INTEGER NOT NULL REFERENCES assignments(id),
  child_id INTEGER NOT NULL REFERENCES children(id),
  target_qq TEXT NOT NULL,
  message TEXT NOT NULL,
  scheduled_at TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('success', 'failed')),
  error_message TEXT,
  created_at TEXT NOT NULL
);
```

Update `create_app()` to initialize the database during app startup using FastAPI lifespan.

**Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_database.py tests/test_health.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add app/database.py app/main.py tests/test_database.py
git commit -m "feat: add SQLite schema"
```

## Task 3: Children API

**Files:**
- Create: `app/schemas.py`
- Create: `app/children.py`
- Create: `tests/test_children_api.py`
- Modify: `app/main.py`

**Step 1: Write failing API tests**

Create `tests/test_children_api.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path):
    app = create_app(database_path=tmp_path / "test.sqlite3", start_scheduler=False)
    return TestClient(app)


def test_create_child(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post("/api/children", json={"name": "小明", "qq_number": "123456"})

    assert response.status_code == 201
    assert response.json()["name"] == "小明"
    assert response.json()["qq_number"] == "123456"


def test_create_child_rejects_invalid_qq(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post("/api/children", json={"name": "小明", "qq_number": "abc"})

    assert response.status_code == 422


def test_list_children_includes_assignment_count(tmp_path):
    with make_client(tmp_path) as client:
        client.post("/api/children", json={"name": "小明", "qq_number": "123456"})
        response = client.get("/api/children")

    assert response.status_code == 200
    assert response.json()[0]["assignment_count"] == 0
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_children_api.py -v
```

Expected: FAIL because child routes do not exist.

**Step 3: Implement schemas and routes**

In `app/schemas.py`, add Pydantic models:

- `ChildCreate`
- `ChildUpdate`
- `ChildRead`

Validation:

- `name`: non-empty after stripping.
- `qq_number`: non-empty digits only.

In `app/children.py`, add an `APIRouter` with:

- `GET /api/children`
- `POST /api/children`
- `PATCH /api/children/{child_id}`

Use direct SQL repository functions inside this module or small private helpers. Keep response shape stable:

```json
{
  "id": 1,
  "name": "小明",
  "qq_number": "123456",
  "assignment_count": 0,
  "last_reminded_at": null,
  "created_at": "...",
  "updated_at": "..."
}
```

Register the router in `app/main.py`.

**Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_children_api.py tests/test_database.py tests/test_health.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add app/schemas.py app/children.py app/main.py tests/test_children_api.py
git commit -m "feat: add children API"
```

## Task 4: Assignments API and Cancellation

**Files:**
- Create: `app/assignments.py`
- Create: `tests/test_assignments_api.py`
- Modify: `app/schemas.py`
- Modify: `app/main.py`

**Step 1: Write failing assignment tests**

Create `tests/test_assignments_api.py`:

```python
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path):
    app = create_app(database_path=tmp_path / "test.sqlite3", start_scheduler=False)
    return TestClient(app)


def create_child(client):
    return client.post("/api/children", json={"name": "小明", "qq_number": "123456"}).json()


def future_time():
    return (datetime.now() + timedelta(hours=1)).replace(microsecond=0).isoformat()


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


def test_cancel_pending_assignment(tmp_path):
    with make_client(tmp_path) as client:
        child = create_child(client)
        assignment = client.post(
            "/api/assignments",
            json={
                "child_id": child["id"],
                "title": "数学练习",
                "description": "",
                "remind_at": future_time(),
            },
        ).json()
        response = client.patch(f"/api/assignments/{assignment['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_assignments_api.py -v
```

Expected: FAIL because assignment routes do not exist.

**Step 3: Implement assignment schemas and routes**

In `app/schemas.py`, add:

- `AssignmentCreate`
- `AssignmentRead`

Validation:

- `title`: non-empty after stripping.
- `remind_at`: valid ISO datetime and greater than current local time.
- `description`: optional string, stored as `""` when absent.

In `app/assignments.py`, add:

- `GET /api/assignments`: return assignments joined with child name and QQ, ordered by `remind_at`.
- `POST /api/assignments`: create pending assignment if child exists.
- `PATCH /api/assignments/{assignment_id}/cancel`: cancel only pending assignments.

Register the router in `app/main.py`.

**Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_assignments_api.py tests/test_children_api.py tests/test_database.py tests/test_health.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add app/assignments.py app/schemas.py app/main.py tests/test_assignments_api.py
git commit -m "feat: add assignments API"
```

## Task 5: Reminder Processing Service

**Files:**
- Create: `app/reminders.py`
- Create: `tests/test_reminders.py`
- Modify: `app/main.py`

**Step 1: Write failing reminder tests**

Create `tests/test_reminders.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_reminders.py -v
```

Expected: FAIL because reminder service and logs API do not exist.

**Step 3: Implement reminder service and logs API**

In `app/reminders.py`, add:

- `build_message(child_name, title, description)`.
- `process_due_reminders(database_path, now=None) -> int`.
- `run_reminder_loop(database_path, interval_seconds=30)` async loop for production startup.

Processing rules:

- Select due assignments where `status = 'pending'` and `remind_at <= now`.
- For each due assignment, build message:

```text
作业提醒：{孩子姓名}，现在该写作业了。
作业：{标题}
说明：{说明}
```

- Omit the `说明` line if description is empty.
- In one transaction, update assignment to `reminded` with `WHERE id = ? AND status = 'pending'`, then insert a `success` reminder log only when the update affected one row.
- If processing one assignment raises, insert a `failed` log when possible and continue with the next due assignment.

Add `GET /api/reminder-logs` route, either in `app/reminders.py` router or a small `app/logs.py`.

Update `app/main.py` lifespan:

- Initialize database.
- If `start_scheduler=True`, create the reminder loop task.
- Cancel the task on shutdown.

**Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_reminders.py tests/test_assignments_api.py tests/test_children_api.py tests/test_database.py tests/test_health.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add app/reminders.py app/main.py tests/test_reminders.py
git commit -m "feat: process due reminders"
```

## Task 6: Static Web Management UI

**Files:**
- Create: `app/static/index.html`
- Create: `app/static/styles.css`
- Create: `app/static/app.js`
- Modify: `app/main.py`

**Step 1: Write a minimal smoke test**

Create or extend `tests/test_health.py`:

```python
def test_root_serves_management_page(tmp_path):
    app = create_app(database_path=tmp_path / "test.sqlite3", start_scheduler=False)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "催孩子写作业" in response.text
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_health.py::test_root_serves_management_page -v
```

Expected: FAIL because the root page does not exist.

**Step 3: Implement frontend files**

`index.html` should include:

- App title.
- Child form: name and QQ.
- Assignment form: child select, title, description, remind time.
- Children list.
- Assignments list with cancel button for pending assignments.
- Reminder log table.

`app.js` should include:

- `loadChildren()`
- `loadAssignments()`
- `loadReminderLogs()`
- `createChild(event)`
- `createAssignment(event)`
- `cancelAssignment(id)`
- `refreshAll()`
- `setInterval(refreshAll, 15000)`

Use `fetch()` against the APIs. Show validation errors near the related forms and keep the UI usable if one request fails.

`styles.css` should keep the interface dense and calm:

- Full-width app shell with constrained content.
- Clear table/list layouts.
- Compact forms.
- Status badges for `pending`, `reminded`, and `cancelled`.
- No marketing hero.

Update `app/main.py` to serve:

- `GET /` -> `app/static/index.html`
- static assets under `/static`

**Step 4: Run smoke test**

Run:

```bash
uv run pytest tests/test_health.py -v
```

Expected: PASS.

**Step 5: Manual browser verification**

Run:

```bash
uv run uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

Verify:

- Add child.
- Create assignment one or two minutes in the future.
- Wait for reminder processing.
- Confirm assignment becomes `reminded`.
- Confirm a simulated QQ log appears.
- Cancel a pending assignment and confirm it does not produce a log.

**Step 6: Commit**

```bash
git add app/main.py app/static/index.html app/static/styles.css app/static/app.js tests/test_health.py
git commit -m "feat: add local management UI"
```

## Task 7: README and End-to-End Verification

**Files:**
- Modify: `README.md`

**Step 1: Update README**

Document:

- What the MVP does.
- What it intentionally does not do.
- Setup:

```bash
uv sync
```

- Run tests:

```bash
uv run pytest
```

- Start app:

```bash
uv run uvicorn app.main:app --reload
```

- Open:

```text
http://127.0.0.1:8000
```

- SQLite database location:

```text
data/assignment_reminder.sqlite3
```

**Step 2: Run full test suite**

Run:

```bash
uv run pytest
```

Expected: all tests PASS.

**Step 3: Run the app and test the MVP manually**

Run:

```bash
uv run uvicorn app.main:app --reload
```

Manual acceptance:

- Add a child with QQ.
- Create a reminder.
- Wait until it is due.
- Confirm one log is created.
- Refresh page and confirm data persists.

**Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document local MVP usage"
```

## Final Verification Checklist

- `uv run pytest` passes.
- `uv run uvicorn app.main:app --reload` starts without errors.
- Browser can open `http://127.0.0.1:8000`.
- Child creation works.
- Assignment creation works.
- Due reminders become `reminded`.
- Simulated QQ reminder logs are written once.
- Cancelled assignments do not create logs.
- README matches actual commands and behavior.

## Implementation Notes

- Keep SQL explicit and small. Do not introduce an ORM for this MVP unless implementation pressure proves it is needed.
- Keep sender behavior isolated in `app/reminders.py`; future real QQ integration should not change assignment APIs.
- Keep datetime handling local and documented. Do not add timezone conversion in MVP.
- Avoid deleting children with existing assignments in the UI; edit is enough for MVP.
