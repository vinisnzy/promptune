import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from promptune.core.config import Settings, get_settings
from promptune.core.logging import setup_logging
from promptune.database.session import build_engine, build_session_maker
from promptune.middleware.request_context import register_request_context_middleware
from promptune.routers.agent import router as agent_router
from promptune.routers.prompt import router as prompt_router

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = build_engine(settings)
        session_maker = build_session_maker(engine)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_maker = session_maker
        logger.info("Application started", extra={"event": "application_started"})
        try:
            yield
        finally:
            await engine.dispose()
            logger.info("Application stopped", extra={"event": "application_stopped"})

    app = FastAPI(lifespan=lifespan)
    register_request_context_middleware(app)
    app.include_router(agent_router)
    app.include_router(prompt_router)

    @app.get("/")
    def read_root() -> dict:
        return {"message": "Welcome to the Promptune!"}

    return app


app = create_app()
