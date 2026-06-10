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
