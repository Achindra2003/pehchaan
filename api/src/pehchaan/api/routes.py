from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pydantic import ValidationError

from pehchaan.api.deps import get_checks, get_store, require_api_key
from pehchaan.config import Settings, get_settings
from pehchaan.domain.models import VerificationPayload, VerificationResult
from pehchaan.domain.policy import EventPolicy, EventRules
from pehchaan.pipeline.checks import Check
from pehchaan.pipeline.service import verify
from pehchaan.store.memory import MemoryStore

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])

Store = Annotated[MemoryStore, Depends(get_store)]

ID_MEDIA_TYPES = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png", b"%PDF-": "application/pdf"}
SELFIE_MEDIA_TYPES = {"image/jpeg", "image/png"}


@router.put("/events/{event_id}/policy", response_model=EventPolicy)
async def put_policy(event_id: str, rules: EventRules, store: Store) -> EventPolicy:
    return store.put_policy(event_id, rules)


@router.get("/events/{event_id}/policy", response_model=EventPolicy)
async def get_policy(event_id: str, store: Store) -> EventPolicy:
    policy = store.get_policy(event_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event policy not found")
    return policy


@router.post("/verifications", response_model=VerificationResult)
async def create_verification(
    payload: Annotated[str, Form(description="VerificationPayload as JSON")],
    id_image: Annotated[UploadFile, File(description="JPEG, PNG or e-Aadhaar PDF")],
    store: Store,
    checks: Annotated[dict[str, Check], Depends(get_checks)],
    settings: Annotated[Settings, Depends(get_settings)],
    selfie: Annotated[UploadFile | None, File()] = None,
    idempotency_key: Annotated[str | None, Header(max_length=128)] = None,
) -> VerificationResult:
    if idempotency_key and (existing := store.find_by_idempotency_key(idempotency_key)):
        return existing

    try:
        body = VerificationPayload.model_validate_json(payload)
    except ValidationError as exc:
        # Never echo submitted values back: they are personal data.
        errors = json.loads(exc.json(include_input=False, include_url=False))
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, errors) from None

    policy = store.get_policy(body.event_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event policy not found")

    image = await _read_limited(id_image, settings.max_upload_bytes)
    media_type = _sniff(image)
    if media_type is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "ID must be JPEG, PNG or PDF")

    selfie_bytes = await _read_limited(selfie, settings.max_upload_bytes) if selfie else None
    if selfie_bytes is not None and _sniff(selfie_bytes) not in SELFIE_MEDIA_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Selfie must be JPEG or PNG")

    result = await verify(body, policy, image, media_type, selfie_bytes, checks)
    store.save_verification(result, idempotency_key)
    return result


@router.get("/verifications/{verification_id}", response_model=VerificationResult)
async def get_verification(verification_id: str, store: Store) -> VerificationResult:
    result = store.get_verification(verification_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification not found")
    return result


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large")
    return data


def _sniff(data: bytes) -> str | None:
    return next((kind for magic, kind in ID_MEDIA_TYPES.items() if data.startswith(magic)), None)
