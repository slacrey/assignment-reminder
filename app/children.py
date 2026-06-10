from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from fastapi import APIRouter, HTTPException, Request, status

from app.database import connect
from app.schemas import ChildCreate, ChildRead, ChildUpdate


router = APIRouter(prefix="/api/children", tags=["children"])


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _fetch_child(connection: sqlite3.Connection, child_id: int) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
          c.id,
          c.name,
          c.qq_number,
          (
            SELECT COUNT(*)
            FROM assignments AS a
            WHERE a.child_id = c.id
          ) AS assignment_count,
          (
            SELECT MAX(rl.sent_at)
            FROM reminder_logs AS rl
            WHERE rl.child_id = c.id
          ) AS last_reminded_at,
          c.created_at,
          c.updated_at
        FROM children AS c
        WHERE c.id = ?
        """,
        (child_id,),
    ).fetchone()


def _database_path(request: Request) -> Path:
    return request.app.state.database_path


def _serialize_child(row: sqlite3.Row) -> ChildRead:
    return ChildRead.model_validate(dict(row))


@router.get("", response_model=list[ChildRead])
def list_children(request: Request) -> list[ChildRead]:
    with connect(_database_path(request)) as connection:
        rows = connection.execute(
            """
            SELECT
              c.id,
              c.name,
              c.qq_number,
              (
                SELECT COUNT(*)
                FROM assignments AS a
                WHERE a.child_id = c.id
              ) AS assignment_count,
              (
                SELECT MAX(rl.sent_at)
                FROM reminder_logs AS rl
                WHERE rl.child_id = c.id
              ) AS last_reminded_at,
              c.created_at,
              c.updated_at
            FROM children AS c
            ORDER BY c.id
            """
        ).fetchall()

    return [_serialize_child(row) for row in rows]


@router.post("", response_model=ChildRead, status_code=status.HTTP_201_CREATED)
def create_child(payload: ChildCreate, request: Request) -> ChildRead:
    now = _now_iso()
    with connect(_database_path(request)) as connection:
        cursor = connection.execute(
            """
            INSERT INTO children (name, qq_number, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (payload.name, payload.qq_number, now, now),
        )
        row = _fetch_child(connection, cursor.lastrowid)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Child was not created",
        )
    return _serialize_child(row)


@router.patch("/{child_id}", response_model=ChildRead)
def update_child(child_id: int, payload: ChildUpdate, request: Request) -> ChildRead:
    updates = payload.model_dump(exclude_unset=True)

    with connect(_database_path(request)) as connection:
        existing = _fetch_child(connection, child_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Child not found",
            )

        if updates:
            assignments = []
            values = []
            for field in ("name", "qq_number"):
                if field in updates:
                    assignments.append(f"{field} = ?")
                    values.append(updates[field])

            assignments.append("updated_at = ?")
            values.append(_now_iso())
            values.append(child_id)

            connection.execute(
                f"UPDATE children SET {', '.join(assignments)} WHERE id = ?",
                values,
            )

        row = _fetch_child(connection, child_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child not found",
        )
    return _serialize_child(row)
