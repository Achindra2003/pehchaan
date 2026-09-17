from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Response, UploadFile, status
from pydantic import ValidationError

from pehchaan.api.deps import get_copilot, get_engines, get_settings, get_store, get_verifier, require_api_key
from pehchaan.config import Settings
from pehchaan.copilot import Copilot, CopilotSummary
from pehchaan.domain.models import (
    REVIEW_DECISIONS,
    Decision,
    ReviewRecord,
    ReviewRequest,
    VerificationPayload,
    VerificationResult,
    VerificationSummary,
)
from pehchaan.domain.policy import EventPolicy, EventRules
from pehchaan.pipeline.engines import Engines
from pehchaan.pipeline.service import Verifier
from pehchaan.store.sqlite import Store

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])

StoreDep = Annotated[Store, Depends(get_store)]

MAGIC = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png", b"%PDF-": "application/pdf"}
SELFIE_MEDIA_TYPES = {"image/jpeg", "image/png"}


# --- events ------------------------------------------------------------------------


@router.get("/events", response_model=list[EventPolicy])
async def list_events(store: StoreDep) -> list[EventPolicy]:
    return store.list_policies()


@router.put("/events/{event_id}/policy", response_model=EventPolicy)
async def put_policy(event_id: str, rules: EventRules, store: StoreDep) -> EventPolicy:
    return store.put_policy(event_id, rules)


@router.get("/events/{event_id}/policy", response_model=EventPolicy)
async def get_policy(event_id: str, store: StoreDep) -> EventPolicy:
    if (policy := store.get_policy(event_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event policy not found")
    return policy


# --- verifications ------------------------------------------------------------------------


@router.post("/verifications", response_model=VerificationResult)
async def create_verification(
    payload: Annotated[str, Form(description="VerificationPayload as JSON")],
    id_image: Annotated[UploadFile, File(description="JPEG, PNG or e-Aadhaar PDF")],
    store: StoreDep,
    verifier: Annotated[Verifier, Depends(get_verifier)],
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
    if (media_type := _sniff(image)) is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "ID must be JPEG, PNG or PDF")
    selfie_bytes = await _read_limited(selfie, settings.max_upload_bytes) if selfie else None
    if selfie_bytes is not None and _sniff(selfie_bytes) not in SELFIE_MEDIA_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Selfie must be JPEG or PNG")

    return await verifier.verify(body, policy, image, media_type, selfie_bytes, idempotency_key)


@router.get("/verifications", response_model=list[VerificationSummary])
async def list_verifications(
    store: StoreDep,
    event_id: str | None = None,
    decision: Decision | None = None,
    open_only: bool = False,
    limit: int = 200,
) -> list[VerificationSummary]:
    return store.list_verifications(event_id, decision, open_only, min(limit, 500))


@router.get("/verifications/{verification_id}", response_model=VerificationResult)
async def get_verification(verification_id: str, store: StoreDep) -> VerificationResult:
    return _load(store, verification_id)


@router.get("/verifications/{verification_id}/images/{kind}")
async def get_image(verification_id: str, kind: Literal["id", "selfie"], store: StoreDep) -> Response:
    blob = store.load_blob(verification_id, kind)
    if blob is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found or already deleted")
    store.audit("image.viewed", verification_id, {"kind": kind})
    media_type, data = blob
    return Response(data, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.post("/verifications/{verification_id}/review", response_model=VerificationResult)
async def review_verification(
    verification_id: str,
    review: ReviewRequest,
    store: StoreDep,
    verifier: Annotated[Verifier, Depends(get_verifier)],
) -> VerificationResult:
    _load(store, verification_id)
    record = ReviewRecord(**review.model_dump(), reviewed_at=datetime.now(UTC))
    result = store.add_review(verification_id, record, REVIEW_DECISIONS[review.action])
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification not found")
    verifier.webhooks.send("verification.reviewed", result)
    return result


@router.get("/verifications/{verification_id}/copilot", response_model=CopilotSummary)
async def copilot_summary(
    verification_id: str, store: StoreDep, copilot: Annotated[Copilot, Depends(get_copilot)]
) -> CopilotSummary:
    return await copilot.summarise(_load(store, verification_id))


@router.get("/verifications/{verification_id}/audit")
async def verification_audit(verification_id: str, store: StoreDep) -> list[dict[str, Any]]:
    return store.audit_entries(verification_id)


# --- operations ------------------------------------------------------------------------------


@router.get("/stats")
async def stats(store: StoreDep, event_id: str | None = None) -> dict[str, Any]:
    return store.stats(event_id)


@router.get("/audit/integrity")
async def audit_integrity(store: StoreDep) -> dict[str, Any]:
    return store.verify_audit_chain()


@router.get("/status")
async def engine_status(
    engines: Annotated[Engines, Depends(get_engines)], copilot: Annotated[Copilot, Depends(get_copilot)]
) -> dict[str, Any]:
    return {**engines.status(), "copilot": "llm" if copilot.enabled else "rules"}


def _load(store: Store, verification_id: str) -> VerificationResult:
    if (result := store.get_verification(verification_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification not found")
    return result


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large")
    return data


def _sniff(data: bytes) -> str | None:
    return next((kind for magic, kind in MAGIC.items() if data.startswith(magic)), None)


__all__ = ["router"]
