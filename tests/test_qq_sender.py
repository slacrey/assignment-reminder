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


def test_onebot_sender_reports_non_object_json_response():
    server = onebot_server(response_body=["ok"])
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
    assert "unexpected JSON shape" in result.error_message


def test_onebot_sender_reports_non_object_data_on_success():
    server = onebot_server(response_body={"status": "ok", "data": []})
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
    assert "unexpected data shape" in result.error_message


def test_onebot_sender_reports_missing_message_id_on_success():
    server = onebot_server(response_body={"status": "ok", "data": {}})
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
    assert "message_id" in result.error_message


def test_create_sender_defaults_to_simulated(monkeypatch):
    monkeypatch.delenv("QQ_SENDER", raising=False)

    assert isinstance(create_sender(), SimulatedSender)
