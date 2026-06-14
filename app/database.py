from pathlib import Path
import sqlite3


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(database_path: str | Path) -> sqlite3.Connection:
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(database_path: str | Path) -> None:
    with connect(database_path) as connection:
        connection.executescript(
            """
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
              provider TEXT NOT NULL DEFAULT 'simulated',
              provider_message_id TEXT,
              status TEXT NOT NULL CHECK (status IN ('success', 'failed')),
              error_message TEXT,
              created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_assignments_status_remind_at
            ON assignments (status, remind_at);

            CREATE INDEX IF NOT EXISTS idx_reminder_logs_created_at
            ON reminder_logs (created_at);
            """
        )
        _ensure_column(
            connection,
            "reminder_logs",
            "provider",
            "TEXT NOT NULL DEFAULT 'simulated'",
        )
        _ensure_column(connection, "reminder_logs", "provider_message_id", "TEXT")


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
