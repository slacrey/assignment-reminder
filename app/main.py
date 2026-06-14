import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.assignments import router as assignments_router
from app.children import router as children_router
from app.database import init_db
from app.qq_sender import create_sender
from app.reminders import router as reminders_router
from app.reminders import run_reminder_loop


STATIC_DIR = Path(__file__).parent / "static"


def create_app(database_path: str | Path | None = None, start_scheduler: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db(app.state.database_path)
        app.state.qq_sender = create_sender()
        reminder_task: asyncio.Task[None] | None = None
        if app.state.start_scheduler:
            reminder_task = asyncio.create_task(
                run_reminder_loop(app.state.database_path, sender=app.state.qq_sender)
            )

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

    @app.get("/", include_in_schema=False)
    def management_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    app.include_router(children_router)
    app.include_router(assignments_router)
    app.include_router(reminders_router)

    return app


app = create_app()
