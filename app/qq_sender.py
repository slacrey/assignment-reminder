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

        if not isinstance(data, dict):
            return SendMessageResult(
                provider=self.provider,
                success=False,
                error_message="OneBot returned unexpected JSON shape",
            )

        if data.get("status") != "ok":
            retcode = data.get("retcode")
            wording = data.get("wording") or data.get("message") or "unknown error"
            return SendMessageResult(
                provider=self.provider,
                success=False,
                error_message=(
                    f"OneBot returned status={data.get('status')} "
                    f"retcode={retcode}: {wording}"
                ),
            )

        response_data = {}
        if "data" in data:
            response_data = data["data"]
            if not isinstance(response_data, dict):
                return SendMessageResult(
                    provider=self.provider,
                    success=False,
                    error_message="OneBot returned unexpected data shape",
                )

        message_id = response_data.get("message_id")
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
        return OneBotHttpSender(
            base_url=base_url, access_token=token, timeout_seconds=timeout
        )
    raise ValueError(f"Unsupported QQ_SENDER: {sender_name}")
