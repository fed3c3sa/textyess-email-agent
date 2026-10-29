"""The backend's HTTP API. Run from backend/:

    .venv/bin/uvicorn app.main:create_app --factory --reload

`create_app` builds the shared objects once (settings, brand store, orchestrator
agent with its memory), keeps them in `app.state`, and includes the API routers:
`api/brands.py` for the Setup screen and `api/sessions.py` for the Studio.
The routes hold no logic of their own: they call the functions that already exist.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.agents.orchestrator.agent import build_orchestrator, open_memory
from app.api import brands, sessions
from app.storage.brands import BrandStore


def create_app(settings: Settings | None = None) -> FastAPI:
    """The API, with its own settings. Tests pass settings with a temporary data folder."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.store = BrandStore(settings.data_dir)
        async with open_memory(settings.data_dir / "chat.sqlite") as memory:
            app.state.agent = build_orchestrator(app.state.store, settings, memory)
            yield

    app = FastAPI(title="TextYess email agent", lifespan=lifespan)
    app.add_middleware(  # the frontend runs on another localhost port while developing
        CORSMiddleware, allow_origin_regex=r"http://localhost(:\d+)?", allow_methods=["*"], allow_headers=["*"]
    )
    app.include_router(brands.router)
    app.include_router(sessions.router)
    return app
