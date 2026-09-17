from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from pehchaan.config import Settings, get_settings
from pehchaan.pipeline.checks import Check
from pehchaan.store.memory import MemoryStore


def get_store(request: Request) -> MemoryStore:
    return request.app.state.store


def get_checks(request: Request) -> dict[str, Check]:
    return request.app.state.checks


def require_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    keys = settings.api_key_list
    if not keys:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No API keys configured")
    presented = (x_api_key or "").encode()
    if not any(hmac.compare_digest(presented, key.encode()) for key in keys):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
