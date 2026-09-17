from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, status

from pehchaan.config import Settings
from pehchaan.copilot import Copilot
from pehchaan.pipeline.engines import Engines
from pehchaan.pipeline.service import Verifier
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


def require_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
    key: Annotated[str | None, Query(include_in_schema=False)] = None,
) -> None:
    """X-API-Key header. `?key=` is accepted only so <img> tags in the console can load images in dev."""
    keys = settings.api_key_list
    if not keys:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No API keys configured")
    presented = x_api_key or (key if settings.env != "prod" else None) or ""
    if not any(hmac.compare_digest(presented.encode(), k.encode()) for k in keys):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
