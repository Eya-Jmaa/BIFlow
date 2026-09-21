from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse

import logging
from contextlib import asynccontextmanager

from app.api.artifacts import router as artifacts_router
from app.api.events import router as events_router
from app.api.exports import router as exports_router
from app.api.pipeline import router as pipeline_router
from app.api.projects import router as projects_router
from app.api.query import router as query_router
from app.config import get_settings
from app.logging import configure_logging
from app.security.rate_limit import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db.base import Base
    from app.db.session import engine
    import app.models  # noqa: F401

    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass
    yield


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(
        title="BIFlow API",
        description="Multi-agent Business Intelligence platform",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request, exc):
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

    @app.exception_handler(Exception)
    async def unhandled_error(request, exc):
        if isinstance(exc, HTTPException):
            raise exc
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    status = settings.llm_status
    if not status["active"] and status["reason"]:
        # Loud at boot: a mistyped provider otherwise costs a whole run's
        # worth of interpretation with no error anywhere.
        logging.getLogger("biflow").warning("LLM interpretation is off — %s", status["reason"])

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "service": settings.app_name,
            "llm": settings.llm_status,
        }

    app.include_router(projects_router, prefix="/api")
    app.include_router(pipeline_router, prefix="/api")
    app.include_router(artifacts_router, prefix="/api")
    app.include_router(exports_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(query_router, prefix="/api")
    return app


app = create_app()
