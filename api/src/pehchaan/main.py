from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from pehchaan import __version__
from pehchaan.aadhaar.app_vc import IssuerKeys
from pehchaan.api.routes import public, router
from pehchaan.config import Settings, get_settings
from pehchaan.copilot import Copilot
from pehchaan.domain.models import DocType
from pehchaan.domain.policy import EventRules
from pehchaan.passes import PassAuthority
from pehchaan.pipeline.checks import build_checks
from pehchaan.pipeline.engines import Engines
from pehchaan.pipeline.queue import VerificationQueue
from pehchaan.pipeline.service import Verifier
from pehchaan.security import KeyRing, RateLimiter
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
    "national-hackathon-shadow": EventRules(event_date=date(2026, 12, 5), min_age=18, mode="shadow"),
}
RETENTION_SWEEP_SECONDS = 3600


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    keyring = KeyRing(settings.api_keys.get_secret_value())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engines = Engines.load(settings)
        passes = PassAuthority(engines.crypto, settings.pass_validity_days)
        webhooks = WebhookSender(settings)
        queue = VerificationQueue(settings.workers, settings.queue_size)
        app.state.engines = engines
        app.state.copilot = Copilot(settings)
        app.state.uidai_issuers = IssuerKeys.load(settings.uidai_jwks_path)
        app.state.verifier = Verifier(settings, engines.store, build_checks(engines), passes, webhooks)
        app.state.queue = queue
        queue.start()

        if settings.seed_demo:
            for tenant in keyring.tenants():
                for event_id, rules in DEMO_EVENTS.items():
                    if engines.store.get_policy(event_id) is None:
                        engines.store.put_policy(tenant, event_id, rules)
                break  # demo events belong to the first configured tenant

        sweeper = asyncio.create_task(_retention_sweep(engines, settings))
        logger.info("pehchaan ready: %s", engines.status())
        try:
            yield
        finally:
            sweeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweeper
            await queue.stop()

    app = FastAPI(
        title="Pehchaan",
        version=__version__,
        description="Identity and eligibility verification for hackathon registrations.",
        docs_url="/docs" if settings.env != "prod" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.keyring = keyring
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["X-API-Key", "Idempotency-Key", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if settings.env == "prod":
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response

    app.include_router(router)
    app.include_router(public)

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    if settings.web_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")

    return app


async def _retention_sweep(engines: Engines, settings: Settings) -> None:
    while True:
        purged = await asyncio.to_thread(engines.store.purge_expired, settings.image_retention_days)
        if purged:
            logger.info("retention sweep removed %d records", purged)
        await asyncio.sleep(RETENTION_SWEEP_SECONDS)


def app_factory() -> FastAPI:
    return create_app()
