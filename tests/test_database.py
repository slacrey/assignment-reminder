import sqlite3

from app.database import connect, init_db


def table_names(database_path):
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    return [row[0] for row in rows]


def index_names(database_path, table_name):
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(f"PRAGMA index_list({table_name})").fetchall()
    return {row[1] for row in rows}


def foreign_keys(database_path, table_name):
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
    return {(row[3], row[2], row[4]) for row in rows}


def test_init_db_creates_core_tables(tmp_path):
    database_path = tmp_path / "test.sqlite3"

    init_db(database_path)

    assert table_names(database_path) == ["assignments", "children", "reminder_logs"]
    assert "idx_assignments_status_remind_at" in index_names(database_path, "assignments")
    assert "idx_reminder_logs_created_at" in index_names(database_path, "reminder_logs")
    assert ("child_id", "children", "id") in foreign_keys(database_path, "assignments")
    assert ("assignment_id", "assignments", "id") in foreign_keys(database_path, "reminder_logs")
    assert ("child_id", "children", "id") in foreign_keys(database_path, "reminder_logs")


def test_connect_returns_dict_like_rows(tmp_path):
    database_path = tmp_path / "test.sqlite3"
    init_db(database_path)

    with connect(database_path) as connection:
        row = connection.execute("SELECT 1 AS value").fetchone()

    assert row["value"] == 1


def test_connect_context_manager_closes_connection(tmp_path):
    database_path = tmp_path / "test.sqlite3"
    init_db(database_path)

    with connect(database_path) as connection:
        connection.execute("SELECT 1")

    try:
        connection.execute("SELECT 1")
    except sqlite3.ProgrammingError as error:
        assert "closed" in str(error)
    else:
        raise AssertionError("connection should be closed after leaving context manager")


def test_schema_enforces_assignment_status_check(tmp_path):
    database_path = tmp_path / "test.sqlite3"
    init_db(database_path)

    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO children (name, qq_number, created_at, updated_at)
            VALUES ('小明', '123456', '2026-06-10T10:00:00', '2026-06-10T10:00:00')
            """
        )
        child_id = connection.execute("SELECT id FROM children").fetchone()["id"]

        try:
            connection.execute(
                """
                INSERT INTO assignments (
                  child_id, title, description, remind_at, status, created_at, updated_at
                )
                VALUES (?, '数学练习', '', '2026-06-10T11:00:00', 'unknown',
                        '2026-06-10T10:00:00', '2026-06-10T10:00:00')
                """,
                (child_id,),
            )
        except sqlite3.IntegrityError as error:
            assert "CHECK constraint failed" in str(error)
        else:
            raise AssertionError("invalid assignment status should fail")


def test_schema_enforces_foreign_keys(tmp_path):
    database_path = tmp_path / "test.sqlite3"
    init_db(database_path)

    with connect(database_path) as connection:
        try:
            connection.execute(
                """
                INSERT INTO assignments (
                  child_id, title, description, remind_at, status, created_at, updated_at
                )
                VALUES (999, '数学练习', '', '2026-06-10T11:00:00', 'pending',
                        '2026-06-10T10:00:00', '2026-06-10T10:00:00')
                """
            )
        except sqlite3.IntegrityError as error:
            assert "FOREIGN KEY constraint failed" in str(error)
        else:
            raise AssertionError("assignment with missing child should fail")
