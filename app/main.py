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
