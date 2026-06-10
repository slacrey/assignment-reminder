from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.children import router as children_router
from app.database import init_db


def create_app(database_path: str | Path | None = None, start_scheduler: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db(app.state.database_path)
        yield

    app = FastAPI(title="Assignment Reminder", lifespan=lifespan)
    app.state.database_path = Path(database_path) if database_path else Path("data/assignment_reminder.sqlite3")
    app.state.start_scheduler = start_scheduler

    @app.get("/api/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(children_router)

    return app


app = create_app()
