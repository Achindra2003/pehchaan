from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from pehchaan import __version__
from pehchaan.api.routes import router
from pehchaan.config import Settings, get_settings
from pehchaan.copilot import Copilot
from pehchaan.domain.models import DocType
from pehchaan.domain.policy import EventRules
from pehchaan.pipeline.checks import build_checks
from pehchaan.pipeline.engines import Engines
from pehchaan.pipeline.service import Verifier
from pehchaan.webhooks import WebhookSender

logger = logging.getLogger("pehchaan")

DEMO_EVENTS: dict[str, EventRules] = {
    "ai-build-challenge-blr": EventRules(event_date=date(2026, 9, 18), min_age=18),
    "campus-hack-students": EventRules(
        event_date=date(2026, 10, 11),
        student_only=True,
        accepted_documents=frozenset({DocType.COLLEGE_ID, DocType.AADHAAR, DocType.PAN}),
    ),
    "junior-coders-13-17": EventRules(event_date=date(2026, 11, 14), min_age=13, max_age=17),
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engines = Engines.load(settings)
        app.state.engines = engines
        app.state.copilot = Copilot(settings)
        app.state.verifier = Verifier(engines.store, build_checks(engines), WebhookSender(settings))
        purged = engines.store.purge_expired(settings.image_retention_days)
        if settings.seed_demo:
            for event_id, rules in DEMO_EVENTS.items():
                if engines.store.get_policy(event_id) is None:
                    engines.store.put_policy(event_id, rules)
        logger.info("pehchaan ready: %s, purged %d expired records", engines.status(), purged)
        yield

    app = FastAPI(
        title="Pehchaan",
        version=__version__,
        description="Identity and eligibility verification for hackathon registrations.",
        docs_url="/docs" if settings.env != "prod" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["X-API-Key", "Idempotency-Key", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    app.include_router(router)

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    if settings.web_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")

    return app


def app_factory() -> FastAPI:
    return create_app()
