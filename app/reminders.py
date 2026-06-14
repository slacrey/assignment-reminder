import asyncio
from datetime import UTC, datetime
import logging
from pathlib import Path
import sqlite3

from fastapi import APIRouter, Request

from app.database import connect
from app.qq_sender import SendMessageRequest
from app.qq_sender import create_sender
from app.schemas import ReminderLogRead


router = APIRouter(prefix="/api/reminder-logs", tags=["reminder-logs"])
logger = logging.getLogger(__name__)


def _local_now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now()
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value.replace(microsecond=0).isoformat()


def _audit_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _database_path(request: Request) -> Path:
    return request.app.state.database_path


def build_message(child_name: str, title: str, description: str) -> str:
    lines = [
        f"作业提醒：{child_name}，现在该写作业了。",
        f"作业：{title}",
    ]
    if description:
        lines.append(f"说明：{description}")
    return "\n".join(lines)


def _due_assignments(database_path: str | Path, now_iso: str) -> list[sqlite3.Row]:
    with connect(database_path) as connection:
        return connection.execute(
            """
            SELECT
              a.id,
              a.child_id,
              c.name AS child_name,
              c.qq_number AS target_qq,
              a.title,
              a.description,
              a.remind_at
            FROM assignments AS a
            JOIN children AS c ON c.id = a.child_id
            WHERE a.status = 'pending'
              AND a.remind_at <= ?
            ORDER BY a.remind_at, a.id
            """,
            (now_iso,),
        ).fetchall()


def _insert_failed_log(
    database_path: str | Path,
    assignment: sqlite3.Row,
    message: str,
    sent_at: str,
    provider: str,
    provider_message_id: str | None,
    error_message: str,
) -> None:
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO reminder_logs (
              assignment_id, child_id, target_qq, message, scheduled_at,
              sent_at, provider, provider_message_id, status, error_message, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'failed', ?, ?)
            """,
            (
                assignment["id"],
                assignment["child_id"],
                assignment["target_qq"],
                message,
                assignment["remind_at"],
                sent_at,
                provider,
                provider_message_id,
                error_message,
                sent_at,
            ),
        )


def process_due_reminders(
    database_path: str | Path, now: datetime | None = None, sender=None
) -> int:
    sender = sender or create_sender()
    now_iso = _local_now_iso(now)
    processed = 0

    for assignment in _due_assignments(database_path, now_iso):
        message = ""
        sent_at = _audit_now_iso()
        try:
            message = build_message(
                assignment["child_name"],
                assignment["title"],
                assignment["description"],
            )
            send_result = sender.send(
                SendMessageRequest(
                    target_qq=assignment["target_qq"],
                    message=message,
                )
            )
            if not send_result.success:
                _insert_failed_log(
                    database_path,
                    assignment,
                    message,
                    sent_at,
                    send_result.provider,
                    send_result.provider_message_id,
                    send_result.error_message or "send failed",
                )
                continue

            with connect(database_path) as connection:
                result = connection.execute(
                    """
                    UPDATE assignments
                    SET status = 'reminded', updated_at = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    (sent_at, assignment["id"]),
                )
                if result.rowcount != 1:
                    continue

                connection.execute(
                    """
                    INSERT INTO reminder_logs (
                      assignment_id, child_id, target_qq, message, scheduled_at,
                      sent_at, provider, provider_message_id, status, error_message, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'success', NULL, ?)
                    """,
                    (
                        assignment["id"],
                        assignment["child_id"],
                        assignment["target_qq"],
                        message,
                        assignment["remind_at"],
                        sent_at,
                        send_result.provider,
                        send_result.provider_message_id,
                        sent_at,
                    ),
                )
        except Exception as error:
            try:
                _insert_failed_log(
                    database_path,
                    assignment,
                    message,
                    sent_at,
                    getattr(sender, "provider", "unknown"),
                    None,
                    str(error),
                )
            except Exception:
                pass
            continue

        processed += 1

    return processed


async def run_reminder_loop(
    database_path: str | Path, interval_seconds: int = 30, sender=None
) -> None:
    while True:
        try:
            process_due_reminders(database_path, sender=sender)
        except Exception:
            logger.exception("Reminder scan failed")
        await asyncio.sleep(interval_seconds)


@router.get("", response_model=list[ReminderLogRead])
def list_reminder_logs(request: Request) -> list[ReminderLogRead]:
    with connect(_database_path(request)) as connection:
        rows = connection.execute(
            """
            SELECT
              rl.id,
              rl.assignment_id,
              rl.child_id,
              c.name AS child_name,
              rl.target_qq,
              a.title AS assignment_title,
              rl.message,
              rl.scheduled_at,
              rl.sent_at,
              rl.provider,
              rl.provider_message_id,
              rl.status,
              rl.error_message,
              rl.created_at
            FROM reminder_logs AS rl
            JOIN assignments AS a ON a.id = rl.assignment_id
            JOIN children AS c ON c.id = rl.child_id
            ORDER BY rl.created_at DESC, rl.id DESC
            """
        ).fetchall()

    return [ReminderLogRead.model_validate(dict(row)) for row in rows]
