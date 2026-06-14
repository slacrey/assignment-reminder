# QQ OneBot Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add real QQ private-message delivery through a local OneBot HTTP gateway while preserving the current simulated sender for development and tests.

**Architecture:** Keep the existing FastAPI, SQLite, and background reminder scanner. Introduce a small sender layer with simulated and OneBot HTTP implementations, then make `process_due_reminders()` call the configured sender before deciding whether to mark an assignment as reminded. Extend reminder logs with provider metadata so real delivery can be audited.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite, pytest, standard-library `urllib.request` for local OneBot HTTP calls, static HTML/CSS/JavaScript.

---

## Preconditions

- Approved design: `docs/plans/2026-06-14-qq-onebot-integration-design.md`.
- Current app serves local management UI from `app/static`.
- Existing reminder behavior lives in `app/reminders.py`.
- Run tests with `uv run pytest`.
- Commit after each task.

## Task 1: Extend Reminder Log Schema

**Files:**
- Modify: `app/database.py`
- Modify: `app/schemas.py`
- Modify: `app/reminders.py`
- Modify: `tests/test_database.py`
- Modify: `tests/test_reminders.py`

**Step 1: Write failing database tests**

Add these helpers and tests to `tests/test_database.py`:

```python
def column_names(database_path, table_name):
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def test_reminder_logs_include_provider_metadata(tmp_path):
    database_path = tmp_path / "test.sqlite3"

    init_db(database_path)

    assert {"provider", "provider_message_id"}.issubset(
        column_names(database_path, "reminder_logs")
    )
```

Add this migration compatibility test:

```python
def test_init_db_migrates_existing_reminder_logs_table(tmp_path):
    database_path = tmp_path / "test.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE reminder_logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              assignment_id INTEGER NOT NULL,
              child_id INTEGER NOT NULL,
              target_qq TEXT NOT NULL,
              message TEXT NOT NULL,
              scheduled_at TEXT NOT NULL,
              sent_at TEXT NOT NULL,
              status TEXT NOT NULL CHECK (status IN ('success', 'failed')),
              error_message TEXT,
              created_at TEXT NOT NULL
            )
            """
        )

    init_db(database_path)

    assert {"provider", "provider_message_id"}.issubset(
        column_names(database_path, "reminder_logs")
    )
```

**Step 2: Write failing reminder API test**

Update `REMINDER_LOG_KEYS` in `tests/test_reminders.py` to include:

```python
"provider",
"provider_message_id",
```

In `test_process_due_reminders_marks_assignment_and_writes_log`, add:

```python
assert logs[0]["provider"] == "simulated"
assert logs[0]["provider_message_id"] is None
```

**Step 3: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_database.py tests/test_reminders.py -v
```

Expected: FAIL because the new fields do not exist yet.

**Step 4: Implement schema and API fields**

In `app/database.py`, extend the `CREATE TABLE reminder_logs` statement:

```sql
provider TEXT NOT NULL DEFAULT 'simulated',
provider_message_id TEXT,
```

Add a helper after the table creation script:

```python
def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
```

Call it inside `init_db()` after `executescript()`:

```python
_ensure_column(connection, "reminder_logs", "provider", "TEXT NOT NULL DEFAULT 'simulated'")
_ensure_column(connection, "reminder_logs", "provider_message_id", "TEXT")
```

In `app/schemas.py`, add fields to `ReminderLogRead`:

```python
provider: str
provider_message_id: str | None
```

In `app/reminders.py`, include the new columns in every reminder log insert:

```sql
provider, provider_message_id,
```

For current simulated behavior insert:

```python
"simulated",
None,
```

Update the `SELECT` in `list_reminder_logs()` to return:

```sql
rl.provider,
rl.provider_message_id,
```

**Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_database.py tests/test_reminders.py -v
```

Expected: PASS.

**Step 6: Commit**

```bash
git add app/database.py app/schemas.py app/reminders.py tests/test_database.py tests/test_reminders.py
git commit -m "feat: track QQ sender provider in logs"
```

## Task 2: Add QQ Sender Abstraction

**Files:**
- Create: `app/qq_sender.py`
- Create: `tests/test_qq_sender.py`

**Step 1: Write failing tests**

Create `tests/test_qq_sender.py`:

```python
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from app.qq_sender import OneBotHttpSender
from app.qq_sender import SendMessageRequest
from app.qq_sender import SimulatedSender
from app.qq_sender import create_sender


class RecordingHandler(BaseHTTPRequestHandler):
    response_status = 200
    response_body = {"status": "ok", "retcode": 0, "data": {"message_id": 12345}}
    requests = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        self.__class__.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": json.loads(body),
            }
        )
        payload = json.dumps(self.__class__.response_body).encode("utf-8")
        self.send_response(self.__class__.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


def onebot_server(response_status=200, response_body=None):
    RecordingHandler.requests = []
    RecordingHandler.response_status = response_status
    RecordingHandler.response_body = response_body or {
        "status": "ok",
        "retcode": 0,
        "data": {"message_id": 12345},
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def request():
    return SendMessageRequest(target_qq="123456", message="作业提醒")


def test_simulated_sender_returns_success():
    result = SimulatedSender().send(request())

    assert result.success is True
    assert result.provider == "simulated"
    assert result.provider_message_id is None
    assert result.error_message is None


def test_onebot_sender_posts_private_message():
    server = onebot_server()
    try:
        sender = OneBotHttpSender(
            base_url=f"http://127.0.0.1:{server.server_port}",
            access_token=None,
            timeout_seconds=1,
        )

        result = sender.send(request())
    finally:
        server.shutdown()
        server.server_close()

    assert result.success is True
    assert result.provider == "onebot"
    assert result.provider_message_id == "12345"
    assert RecordingHandler.requests == [
        {
            "path": "/send_private_msg",
            "authorization": None,
            "body": {
                "user_id": 123456,
                "message": "作业提醒",
                "auto_escape": True,
            },
        }
    ]


def test_onebot_sender_sends_access_token():
    server = onebot_server()
    try:
        sender = OneBotHttpSender(
            base_url=f"http://127.0.0.1:{server.server_port}",
            access_token="secret",
            timeout_seconds=1,
        )

        sender.send(request())
    finally:
        server.shutdown()
        server.server_close()

    assert RecordingHandler.requests[0]["authorization"] == "Bearer secret"


def test_onebot_sender_reports_failed_response():
    server = onebot_server(
        response_body={"status": "failed", "retcode": 100, "wording": "not friend"}
    )
    try:
        sender = OneBotHttpSender(
            base_url=f"http://127.0.0.1:{server.server_port}",
            access_token=None,
            timeout_seconds=1,
        )

        result = sender.send(request())
    finally:
        server.shutdown()
        server.server_close()

    assert result.success is False
    assert result.provider == "onebot"
    assert "retcode=100" in result.error_message


def test_create_sender_defaults_to_simulated(monkeypatch):
    monkeypatch.delenv("QQ_SENDER", raising=False)

    assert isinstance(create_sender(), SimulatedSender)
```

**Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/test_qq_sender.py -v
```

Expected: FAIL because `app.qq_sender` does not exist.

**Step 3: Implement sender layer**

Create `app/qq_sender.py`:

```python
from dataclasses import dataclass
import json
import os
from urllib import error, request


@dataclass(frozen=True)
class SendMessageRequest:
    target_qq: str
    message: str


@dataclass(frozen=True)
class SendMessageResult:
    provider: str
    success: bool
    provider_message_id: str | None = None
    error_message: str | None = None


class SimulatedSender:
    provider = "simulated"

    def send(self, payload: SendMessageRequest) -> SendMessageResult:
        return SendMessageResult(provider=self.provider, success=True)


class OneBotHttpSender:
    provider = "onebot"

    def __init__(
        self,
        base_url: str,
        access_token: str | None = None,
        timeout_seconds: float = 5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout_seconds = timeout_seconds

    def send(self, payload: SendMessageRequest) -> SendMessageResult:
        body = json.dumps(
            {
                "user_id": int(payload.target_qq),
                "message": payload.message,
                "auto_escape": True,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        http_request = request.Request(
            f"{self.base_url}/send_private_msg",
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            return SendMessageResult(
                provider=self.provider,
                success=False,
                error_message=f"OneBot HTTP {exc.code}",
            )
        except OSError as exc:
            return SendMessageResult(
                provider=self.provider,
                success=False,
                error_message=f"OneBot request failed: {exc}",
            )

        try:
            data = json.loads(response_body)
        except json.JSONDecodeError:
            return SendMessageResult(
                provider=self.provider,
                success=False,
                error_message="OneBot returned invalid JSON",
            )

        if data.get("status") != "ok":
            retcode = data.get("retcode")
            wording = data.get("wording") or data.get("message") or "unknown error"
            return SendMessageResult(
                provider=self.provider,
                success=False,
                error_message=f"OneBot returned status={data.get('status')} retcode={retcode}: {wording}",
            )

        message_id = (data.get("data") or {}).get("message_id")
        return SendMessageResult(
            provider=self.provider,
            success=True,
            provider_message_id=str(message_id) if message_id is not None else None,
        )


def create_sender():
    sender_name = os.getenv("QQ_SENDER", "simulated").strip().lower()
    if sender_name == "simulated":
        return SimulatedSender()
    if sender_name == "onebot":
        base_url = os.getenv("ONEBOT_BASE_URL", "").strip()
        if not base_url:
            raise ValueError("ONEBOT_BASE_URL is required when QQ_SENDER=onebot")
        timeout = float(os.getenv("ONEBOT_TIMEOUT_SECONDS", "5"))
        token = os.getenv("ONEBOT_ACCESS_TOKEN") or None
        return OneBotHttpSender(base_url=base_url, access_token=token, timeout_seconds=timeout)
    raise ValueError(f"Unsupported QQ_SENDER: {sender_name}")
```

**Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_qq_sender.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add app/qq_sender.py tests/test_qq_sender.py
git commit -m "feat: add QQ sender adapters"
```

## Task 3: Use Sender in Reminder Processing

**Files:**
- Modify: `app/reminders.py`
- Modify: `app/main.py`
- Modify: `tests/test_reminders.py`

**Step 1: Write failing reminder tests**

In `tests/test_reminders.py`, import:

```python
from app.qq_sender import SendMessageResult
```

Add a fake sender:

```python
class FakeSender:
    provider = "fake"

    def __init__(self, result):
        self.result = result
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        return self.result
```

Add a success test:

```python
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
```

Add a failure test:

```python
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
```

**Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_reminders.py -v
```

Expected: FAIL because `process_due_reminders()` does not accept `sender`.

**Step 3: Update reminder processor**

In `app/reminders.py`, import:

```python
from app.qq_sender import SendMessageRequest
from app.qq_sender import create_sender
```

Change the signature:

```python
def process_due_reminders(database_path: str | Path, now: datetime | None = None, sender=None) -> int:
```

At the top:

```python
sender = sender or create_sender()
```

For each due assignment:

1. Build the message.
2. Call:

```python
send_result = sender.send(
    SendMessageRequest(target_qq=assignment["target_qq"], message=message)
)
```

3. If `send_result.success` is false, insert a failed log with `send_result.provider`, `send_result.provider_message_id`, and `send_result.error_message`, then continue without updating assignment status.
4. If success, perform the existing guarded assignment update and success log insert with sender metadata.

Keep `_insert_failed_log()` but change it to accept:

```python
provider: str
provider_message_id: str | None
error_message: str
```

Update `run_reminder_loop()`:

```python
async def run_reminder_loop(database_path: str | Path, interval_seconds: int = 30, sender=None) -> None:
```

Inside the loop:

```python
process_due_reminders(database_path, sender=sender)
```

In `app/main.py`, import `create_sender`, create the sender in lifespan after `init_db`, store it in `app.state.qq_sender`, and pass it to the reminder loop:

```python
app.state.qq_sender = create_sender()
reminder_task = asyncio.create_task(
    run_reminder_loop(app.state.database_path, sender=app.state.qq_sender)
)
```

When `start_scheduler=False`, still create and store the sender so status endpoints can use it later.

**Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_reminders.py tests/test_qq_sender.py -v
```

Expected: PASS.

**Step 5: Run full test suite**

Run:

```bash
uv run pytest
```

Expected: PASS.

**Step 6: Commit**

```bash
git add app/reminders.py app/main.py tests/test_reminders.py
git commit -m "feat: send reminders through QQ sender"
```

## Task 4: Expose Sender Metadata in the UI

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`

**Step 1: Update the log table markup**

In `app/static/index.html`, change the reminder log table header from 6 columns to 7 columns:

```html
<th scope="col">发送方式</th>
```

Place it after `状态`. Update the empty row colspan from `6` to `7`.

**Step 2: Update the renderer**

In `app/static/app.js`, update `renderReminderLogs()`:

```javascript
if (state.logs.length === 0) {
  nodes.reminderLogs.innerHTML = emptyRow("暂无日志", 7);
  return;
}
```

Add a provider cell after status:

```javascript
<td class="cell-muted">
  ${escapeHtml(log.provider || "--")}
  ${log.provider_message_id ? `<span class="cell-muted">#${escapeHtml(log.provider_message_id)}</span>` : ""}
</td>
```

Keep the message cell as the last column.

**Step 3: Manually inspect static rendering**

Run the app:

```bash
uv run uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Expected:

- The reminder log table has a "发送方式" column.
- Empty state spans all columns.
- Existing add-child and add-assignment flows still work.

Stop the server after inspection.

**Step 4: Run tests**

Run:

```bash
uv run pytest
```

Expected: PASS.

**Step 5: Commit**

```bash
git add app/static/index.html app/static/app.js
git commit -m "feat: show QQ sender metadata in logs"
```

## Task 5: Document OneBot Runtime Configuration

**Files:**
- Modify: `README.md`

**Step 1: Update README**

Add this section after "启动应用":

    ## 真实 QQ 发送

    默认使用模拟发送，不会访问 QQ：

    ```bash
    uv run uvicorn app.main:app --reload
    ```

    要发送真实 QQ 私聊消息，先启动一个兼容 OneBot v11 HTTP API 的本地 QQ 网关，例如 NapCat 或 Lagrange。然后设置：

    ```bash
    QQ_SENDER=onebot \
    ONEBOT_BASE_URL=http://127.0.0.1:3000 \
    uv run uvicorn app.main:app --reload
    ```

    如果网关配置了 access token：

    ```bash
    QQ_SENDER=onebot \
    ONEBOT_BASE_URL=http://127.0.0.1:3000 \
    ONEBOT_ACCESS_TOKEN=your-token \
    uv run uvicorn app.main:app --reload
    ```

    发送失败会写入提醒日志，作业保持待提醒状态，下一轮扫描会继续重试。

**Step 2: Run tests**

Run:

```bash
uv run pytest
```

Expected: PASS.

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: explain OneBot QQ setup"
```

## Task 6: Final Verification

**Files:**
- No code changes expected.

**Step 1: Check git status**

Run:

```bash
git status --short
```

Expected: clean working tree.

**Step 2: Run full test suite**

Run:

```bash
uv run pytest
```

Expected: PASS.

**Step 3: Optional local OneBot smoke test**

If a OneBot HTTP gateway is running locally:

```bash
QQ_SENDER=onebot ONEBOT_BASE_URL=http://127.0.0.1:3000 uv run uvicorn app.main:app --reload
```

Create a due assignment and confirm:

- Target QQ receives the message.
- Log status is `success`.
- Provider is `onebot`.
- Provider message ID is visible when returned by the gateway.

If no gateway is available, skip this step and note it in the final handoff.
