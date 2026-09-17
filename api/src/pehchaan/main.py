from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pehchaan import __version__
from pehchaan.api.routes import router
from pehchaan.config import get_settings
from pehchaan.pipeline.checks import default_checks
from pehchaan.store.memory import MemoryStore


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Pehchaan",
        version=__version__,
        description="Identity and eligibility verification for hackathon registrations.",
        docs_url="/docs" if settings.env != "prod" else None,
        redoc_url=None,
    )
    app.state.store = MemoryStore()
    app.state.checks = default_checks()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["X-API-Key", "Idempotency-Key", "Content-Type"],
    )
    app.include_router(router)

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
