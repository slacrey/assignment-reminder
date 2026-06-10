from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from fastapi import APIRouter, HTTPException, Request, status

from app.database import connect
from app.schemas import AssignmentCreate, AssignmentRead


router = APIRouter(prefix="/api/assignments", tags=["assignments"])


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _database_path(request: Request) -> Path:
    return request.app.state.database_path


def _fetch_assignment(
    connection: sqlite3.Connection,
    assignment_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
          a.id,
          a.child_id,
          c.name AS child_name,
          c.qq_number AS child_qq_number,
          a.title,
          a.description,
          a.remind_at,
          a.status,
          a.created_at,
          a.updated_at
        FROM assignments AS a
        JOIN children AS c ON c.id = a.child_id
        WHERE a.id = ?
        """,
        (assignment_id,),
    ).fetchone()


def _serialize_assignment(row: sqlite3.Row) -> AssignmentRead:
    return AssignmentRead.model_validate(dict(row))


@router.get("", response_model=list[AssignmentRead])
def list_assignments(request: Request) -> list[AssignmentRead]:
    with connect(_database_path(request)) as connection:
        rows = connection.execute(
            """
            SELECT
              a.id,
              a.child_id,
              c.name AS child_name,
              c.qq_number AS child_qq_number,
              a.title,
              a.description,
              a.remind_at,
              a.status,
              a.created_at,
              a.updated_at
            FROM assignments AS a
            JOIN children AS c ON c.id = a.child_id
            ORDER BY a.remind_at, a.id
            """
        ).fetchall()

    return [_serialize_assignment(row) for row in rows]


@router.post("", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
def create_assignment(payload: AssignmentCreate, request: Request) -> AssignmentRead:
    now = _now_iso()
    with connect(_database_path(request)) as connection:
        child = connection.execute(
            "SELECT id FROM children WHERE id = ?",
            (payload.child_id,),
        ).fetchone()
        if child is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Child not found",
            )

        cursor = connection.execute(
            """
            INSERT INTO assignments (
              child_id, title, description, remind_at, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                payload.child_id,
                payload.title,
                payload.description,
                payload.remind_at.isoformat(),
                now,
                now,
            ),
        )
        row = _fetch_assignment(connection, cursor.lastrowid)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Assignment was not created",
        )
    return _serialize_assignment(row)


@router.patch("/{assignment_id}/cancel", response_model=AssignmentRead)
def cancel_assignment(assignment_id: int, request: Request) -> AssignmentRead:
    now = _now_iso()
    with connect(_database_path(request)) as connection:
        result = connection.execute(
            """
            UPDATE assignments
            SET status = 'cancelled', updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now, assignment_id),
        )
        if result.rowcount == 0:
            existing = _fetch_assignment(connection, assignment_id)
            if existing is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assignment not found",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Assignment is not pending",
            )

        row = _fetch_assignment(connection, assignment_id)

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )
    return _serialize_assignment(row)
