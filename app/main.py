import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI

from app.assignments import router as assignments_router
from app.children import router as children_router
from app.database import init_db
from app.reminders import router as reminders_router
from app.reminders import run_reminder_loop


def create_app(database_path: str | Path | None = None, start_scheduler: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db(app.state.database_path)
        reminder_task: asyncio.Task[None] | None = None
        if app.state.start_scheduler:
            reminder_task = asyncio.create_task(run_reminder_loop(app.state.database_path))

        try:
            yield
        finally:
            if reminder_task is not None:
                reminder_task.cancel()
                with suppress(asyncio.CancelledError):
                    await reminder_task

    app = FastAPI(title="Assignment Reminder", lifespan=lifespan)
    app.state.database_path = Path(database_path) if database_path else Path("data/assignment_reminder.sqlite3")
    app.state.start_scheduler = start_scheduler

    @app.get("/api/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(children_router)
    app.include_router(assignments_router)
    app.include_router(reminders_router)

    return app


app = create_app()
