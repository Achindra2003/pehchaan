from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, status

from pehchaan.config import Settings
from pehchaan.copilot import Copilot
from pehchaan.pipeline.engines import Engines
from pehchaan.pipeline.queue import VerificationQueue
from pehchaan.pipeline.service import Verifier
from pehchaan.security import KeyRing, Permission, Principal, RateLimiter
from pehchaan.store.sqlite import Store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_engines(request: Request) -> Engines:
    return request.app.state.engines


def get_store(request: Request) -> Store:
    return request.app.state.engines.store


def get_verifier(request: Request) -> Verifier:
    return request.app.state.verifier


def get_copilot(request: Request) -> Copilot:
    return request.app.state.copilot


def get_queue(request: Request) -> VerificationQueue:
    return request.app.state.queue


def authenticate(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
    key: Annotated[str | None, Query(include_in_schema=False)] = None,
) -> Principal:
    """X-API-Key header. `?key=` is accepted outside prod only, so <img> tags can load review images in a demo."""
    keyring: KeyRing = request.app.state.keyring
    settings: Settings = request.app.state.settings
    if not keyring.configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No API keys configured")
    presented = x_api_key or (key if settings.env != "prod" else None)
    principal = keyring.authenticate(presented) if presented else None
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    return principal


def require(permission: Permission) -> Callable[..., Principal]:
    def dependency(principal: Annotated[Principal, Depends(authenticate)]) -> Principal:
        if not principal.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Role '{principal.role}' cannot {permission.value}")
        return principal

    return dependency


def rate_limited(request: Request, principal: Annotated[Principal, Depends(require(Permission.VERIFY))]) -> Principal:
    limiter: RateLimiter = request.app.state.rate_limiter
    allowed, retry_after = limiter.allow(principal.key_id)
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit exceeded",
            headers={"Retry-After": str(max(1, round(retry_after)))},
        )
    return principal
