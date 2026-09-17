from __future__ import annotations

import asyncio
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from pehchaan import jose
from pehchaan.aadhaar import app_vc
from pehchaan.api.deps import (
    get_copilot,
    get_engines,
    get_queue,
    get_settings,
    get_store,
    get_verifier,
    rate_limited,
    require,
)
from pehchaan.config import Settings
from pehchaan.copilot import Copilot, CopilotSummary
from pehchaan.domain.models import (
    REVIEW_DECISIONS,
    Decision,
    Job,
    ObservedOutcome,
    OutcomeRequest,
    PassVerificationRequest,
    RegistrationBase,
    ReviewRecord,
    ReviewRequest,
    VerificationPayload,
    VerificationResult,
    VerificationSummary,
)
from pehchaan.domain.policy import EventPolicy, EventRules
from pehchaan.pipeline.engines import Engines
from pehchaan.pipeline.queue import QueueFullError, VerificationQueue
from pehchaan.pipeline.service import Verifier
from pehchaan.security import Permission, Principal
from pehchaan.store.sqlite import Store, TenantConflictError

router = APIRouter(prefix="/v1")
public = APIRouter()

StoreDep = Annotated[Store, Depends(get_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

MAGIC = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png", b"%PDF-": "application/pdf"}
SELFIE_MEDIA_TYPES = {"image/jpeg", "image/png"}
VC_SESSION_TTL = timedelta(minutes=10)


# --- events ----------------------------------------------------------------------------------------------


@router.get("/events", response_model=list[EventPolicy])
async def list_events(
    store: StoreDep, who: Annotated[Principal, Depends(require(Permission.READ))]
) -> list[EventPolicy]:
    return store.list_policies(who.tenant)


@router.put("/events/{event_id}/policy", response_model=EventPolicy)
async def put_policy(
    event_id: str,
    rules: EventRules,
    store: StoreDep,
    who: Annotated[Principal, Depends(require(Permission.MANAGE_EVENTS))],
) -> EventPolicy:
    try:
        return store.put_policy(who.tenant, event_id, rules)
    except TenantConflictError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Event belongs to another tenant") from None


@router.get("/events/{event_id}/policy", response_model=EventPolicy)
async def get_policy(
    event_id: str, store: StoreDep, who: Annotated[Principal, Depends(require(Permission.READ))]
) -> EventPolicy:
    return _policy(store, event_id, who.tenant)


# --- verifications ---------------------------------------------------------------------------------------------


@router.post(
    "/verifications",
    response_model=VerificationResult,
    responses={202: {"model": Job, "description": "Accepted; poll /v1/jobs/{job_id} or wait for the webhook"}},
)
async def create_verification(
    payload: Annotated[str, Form(description="VerificationPayload as JSON")],
    id_image: Annotated[UploadFile, File(description="JPEG, PNG or e-Aadhaar PDF")],
    store: StoreDep,
    settings: SettingsDep,
    verifier: Annotated[Verifier, Depends(get_verifier)],
    queue: Annotated[VerificationQueue, Depends(get_queue)],
    who: Annotated[Principal, Depends(rate_limited)],
    selfie: Annotated[UploadFile | None, File()] = None,
    idempotency_key: Annotated[str | None, Header(max_length=128)] = None,
    mode: Literal["sync", "async"] = "sync",
) -> Any:
    if idempotency_key and (existing := store.find_by_idempotency_key(who.tenant, idempotency_key)):
        return existing
    body = _parse(VerificationPayload, payload)
    _require_consent(settings, body)
    policy = _policy(store, body.event_id, who.tenant)

    image = await _read_limited(id_image, settings.max_upload_bytes)
    if (media_type := _sniff(image)) is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "ID must be JPEG, PNG or PDF")
    selfie_bytes = await _read_limited(selfie, settings.max_upload_bytes) if selfie else None
    if selfie_bytes is not None and _sniff(selfie_bytes) not in SELFIE_MEDIA_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Selfie must be JPEG or PNG")

    try:
        task = queue.submit(
            who.tenant,
            lambda: verifier.verify_document(
                who.tenant, body, policy, image, media_type, selfie_bytes, idempotency_key
            ),
        )
    except QueueFullError:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Verification queue is full", headers={"Retry-After": "5"}
        ) from None
    accepted = JSONResponse(
        status_code=status.HTTP_202_ACCEPTED, content=Job(job_id=task.job_id, status="queued").model_dump()
    )
    if mode == "async":
        return accepted
    try:
        return await asyncio.wait_for(asyncio.shield(task.future), timeout=settings.sync_timeout_seconds)
    except TimeoutError:
        return accepted


@router.post("/verifications/pass", response_model=VerificationResult)
async def verify_with_pass(
    request: PassVerificationRequest,
    store: StoreDep,
    settings: SettingsDep,
    verifier: Annotated[Verifier, Depends(get_verifier)],
    who: Annotated[Principal, Depends(rate_limited)],
    idempotency_key: Annotated[str | None, Header(max_length=128)] = None,
) -> VerificationResult:
    """Returning participant: no document, no OCR, a few milliseconds."""
    if idempotency_key and (existing := store.find_by_idempotency_key(who.tenant, idempotency_key)):
        return existing
    _require_consent(settings, request)
    policy = _policy(store, request.event_id, who.tenant)
    return await verifier.verify_pass(who.tenant, request, policy, idempotency_key)


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(
    job_id: str,
    queue: Annotated[VerificationQueue, Depends(get_queue)],
    who: Annotated[Principal, Depends(require(Permission.READ))],
) -> Job:
    if (job := queue.job(job_id, who.tenant)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


@router.get("/verifications", response_model=list[VerificationSummary])
async def list_verifications(
    store: StoreDep,
    who: Annotated[Principal, Depends(require(Permission.READ))],
    event_id: str | None = None,
    decision: Decision | None = None,
    open_only: bool = False,
    limit: int = 200,
) -> list[VerificationSummary]:
    """With open_only, this is the review queue: highest priority first (duplicates, low confidence, minors)."""
    return store.list_verifications(who.tenant, event_id, decision, open_only, min(limit, 500))


@router.get("/verifications/{verification_id}", response_model=VerificationResult)
async def get_verification(
    verification_id: str, store: StoreDep, who: Annotated[Principal, Depends(require(Permission.READ))]
) -> VerificationResult:
    return _load(store, verification_id, who.tenant)


@router.get("/verifications/{verification_id}/images/{kind}")
async def get_image(
    verification_id: str,
    kind: Literal["id", "selfie"],
    store: StoreDep,
    who: Annotated[Principal, Depends(require(Permission.VIEW_IMAGES))],
) -> Response:
    _load(store, verification_id, who.tenant)
    blob = store.load_blob(verification_id, kind)
    if blob is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not stored or already deleted")
    store.audit("image.viewed", verification_id, {"kind": kind, "key": who.key_id}, who.tenant)
    media_type, data = blob
    return Response(data, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.post("/verifications/{verification_id}/review", response_model=VerificationResult)
async def review_verification(
    verification_id: str,
    review: ReviewRequest,
    store: StoreDep,
    settings: SettingsDep,
    verifier: Annotated[Verifier, Depends(get_verifier)],
    who: Annotated[Principal, Depends(require(Permission.REVIEW))],
) -> VerificationResult:
    _load(store, verification_id, who.tenant)
    record = ReviewRecord(**review.model_dump(), reviewed_at=datetime.now(UTC))
    result = store.add_review(verification_id, record, REVIEW_DECISIONS[review.action])
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification not found")
    if settings.image_storage == "review_only" and store.delete_blobs(verification_id):
        store.audit("image.deleted", verification_id, {"reason": "review closed"}, who.tenant)
    verifier.webhooks.send("verification.reviewed", result)
    return result


@router.post("/verifications/{verification_id}/outcome", response_model=VerificationResult)
async def record_outcome(
    verification_id: str,
    outcome: OutcomeRequest,
    store: StoreDep,
    who: Annotated[Principal, Depends(require(Permission.VERIFY))],
) -> VerificationResult:
    """Shadow mode: Hackingly reports what its existing process decided, so agreement can be measured."""
    _load(store, verification_id, who.tenant)
    result = store.record_outcome(
        verification_id, ObservedOutcome(**outcome.model_dump(), recorded_at=datetime.now(UTC))
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification not found")
    return result


@router.delete("/verifications/{verification_id}", response_model=VerificationResult)
async def erase_verification(
    verification_id: str, store: StoreDep, who: Annotated[Principal, Depends(require(Permission.ERASE))]
) -> VerificationResult:
    """DPDP erasure request: images, face data and index entries are deleted; a minimal decision record stays."""
    _load(store, verification_id, who.tenant)
    result = store.erase(verification_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification not found")
    return result


@router.get("/verifications/{verification_id}/copilot", response_model=CopilotSummary)
async def copilot_summary(
    verification_id: str,
    store: StoreDep,
    copilot: Annotated[Copilot, Depends(get_copilot)],
    who: Annotated[Principal, Depends(require(Permission.REVIEW))],
) -> CopilotSummary:
    return await copilot.summarise(_load(store, verification_id, who.tenant))


@router.get("/verifications/{verification_id}/audit")
async def verification_audit(
    verification_id: str, store: StoreDep, who: Annotated[Principal, Depends(require(Permission.READ))]
) -> list[dict[str, Any]]:
    _load(store, verification_id, who.tenant)
    return store.audit_entries(who.tenant, verification_id)


# --- passes ------------------------------------------------------------------------------------------------------


class RevokeRequest(BaseModel):
    reason: str = "revoked by platform"


@router.post("/passes/{pass_id}/revoke")
async def revoke_pass(
    pass_id: str,
    body: RevokeRequest,
    store: StoreDep,
    who: Annotated[Principal, Depends(require(Permission.MANAGE_EVENTS))],
) -> dict[str, Any]:
    if not store.revoke_pass(pass_id, who.tenant, body.reason[:120]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pass not found or already revoked")
    return {"pass_id": pass_id, "revoked": True}


# --- Aadhaar App (OpenID4VP) --------------------------------------------------------------------------------------


class AadhaarAppSession(BaseModel):
    session_id: str
    qr_uri: str
    request_uri: str
    requested_claims: list[str]
    expires_at: datetime


@router.post("/aadhaar-app/sessions", response_model=AadhaarAppSession)
async def start_aadhaar_app_session(
    registration: RegistrationBase,
    store: StoreDep,
    settings: SettingsDep,
    who: Annotated[Principal, Depends(rate_limited)],
) -> AadhaarAppSession:
    """Start a verification the participant completes by scanning a QR with the Aadhaar App."""
    _require_consent(settings, registration)
    policy = _policy(store, registration.event_id, who.tenant)
    session_id = f"vcs_{secrets.token_urlsafe(18)}"
    store.create_vc_session(
        session_id, who.tenant, secrets.token_urlsafe(24), json.loads(registration.model_dump_json()), VC_SESSION_TTL
    )
    request_uri = f"{settings.public_base_url}/aadhaar-app/requests/{session_id}"
    qr_uri = "openid4vp://?" + urlencode({"client_id": settings.verifier_client_id, "request_uri": request_uri})
    return AadhaarAppSession(
        session_id=session_id,
        qr_uri=qr_uri,
        request_uri=request_uri,
        requested_claims=app_vc.requested_claims(policy),
        expires_at=datetime.now(UTC) + VC_SESSION_TTL,
    )


@router.get("/aadhaar-app/sessions/{session_id}")
async def aadhaar_app_session_status(
    session_id: str, store: StoreDep, who: Annotated[Principal, Depends(require(Permission.READ))]
) -> dict[str, Any]:
    session = store.get_vc_session(session_id)
    if session is None or session.tenant != who.tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return {"session_id": session_id, "status": session.status, "verification_id": session.verification_id}


@public.get("/aadhaar-app/requests/{session_id}", include_in_schema=True, tags=["aadhaar-app"])
async def aadhaar_app_request(session_id: str, request: Request) -> Response:
    """Fetched by the Aadhaar App (request_uri): a signed OpenID4VP request asking only for what the event needs."""
    engines: Engines = request.app.state.engines
    settings: Settings = request.app.state.settings
    session = engines.store.get_vc_session(session_id)
    if session is None or session.status != "pending" or session.expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request expired or unknown")
    policy = _policy(engines.store, session.request["event_id"], session.tenant)
    token = app_vc.request_object(
        session_id=session_id,
        nonce=session.nonce,
        client_id=settings.verifier_client_id,
        response_uri=f"{settings.public_base_url}/aadhaar-app/callback",
        claims=app_vc.requested_claims(policy),
        key=engines.crypto.signing_key,
    )
    return Response(token, media_type="application/oauth-authz-req+jwt")


class AadhaarAppCallback(BaseModel):
    txn: str
    token: str


@public.post("/aadhaar-app/callback", tags=["aadhaar-app"])
async def aadhaar_app_callback(body: AadhaarAppCallback, request: Request) -> dict[str, str]:
    """Posted by the Aadhaar App with the resident's SD-JWT presentation."""
    engines: Engines = request.app.state.engines
    settings: Settings = request.app.state.settings
    verifier: Verifier = request.app.state.verifier
    store = engines.store
    session = store.get_vc_session(body.txn)
    if session is None or session.status != "pending" or session.expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown or expired transaction")

    claims, error = None, None
    try:
        claims = app_vc.verify_presentation(
            body.token, request.app.state.uidai_issuers, audience=settings.verifier_client_id, nonce=session.nonce
        )
    except app_vc.PresentationError as exc:
        error = str(exc)
    payload = VerificationPayload(**session.request)
    policy = _policy(store, payload.event_id, session.tenant)
    result = await verifier.verify_aadhaar_app(session.tenant, payload, policy, claims, error)
    if not store.complete_vc_session(body.txn, "completed" if claims else "failed", result.verification_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Transaction already completed")
    return {"txn": body.txn, "responseCode": "200", "message": "received"}


@public.get("/.well-known/jwks.json", tags=["ops"])
async def jwks(request: Request) -> dict[str, Any]:
    """Public key for verifying Pehchaan Passes and OpenID4VP request objects."""
    key = request.app.state.engines.crypto.signing_key.public_key()
    return {"keys": [{**jose.public_jwk(key), "kid": jose.key_id(key), "use": "sig", "alg": "ES256"}]}


# --- operations -----------------------------------------------------------------------------------------------------


@router.get("/stats")
async def stats(
    store: StoreDep, who: Annotated[Principal, Depends(require(Permission.READ))], event_id: str | None = None
) -> dict[str, Any]:
    return store.stats(who.tenant, event_id)


@router.get("/usage")
async def usage(
    store: StoreDep,
    settings: SettingsDep,
    who: Annotated[Principal, Depends(require(Permission.BILLING))],
    event_id: str | None = None,
) -> dict[str, Any]:
    return store.usage(who.tenant, event_id, settings.manual_review_minutes)


@router.get("/audit/integrity")
async def audit_integrity(
    store: StoreDep, _: Annotated[Principal, Depends(require(Permission.AUDIT))]
) -> dict[str, Any]:
    return store.verify_audit_chain()


@router.get("/status")
async def engine_status(
    engines: Annotated[Engines, Depends(get_engines)],
    copilot: Annotated[Copilot, Depends(get_copilot)],
    queue: Annotated[VerificationQueue, Depends(get_queue)],
    request: Request,
    _: Annotated[Principal, Depends(require(Permission.READ))],
) -> dict[str, Any]:
    return {
        **engines.status(),
        "aadhaar_app_issuer_keys": len(request.app.state.uidai_issuers.keys),
        "copilot": "llm" if copilot.enabled else "rules",
        "queue": {"waiting": queue.depth, "running": queue.running},
    }


# --- helpers ---------------------------------------------------------------------------------------------------------


def _parse(model: type[VerificationPayload], raw: str) -> VerificationPayload:
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        # Never echo submitted values back: they are personal data.
        errors = json.loads(exc.json(include_input=False, include_url=False))
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, errors) from None


def _require_consent(settings: Settings, registration: RegistrationBase) -> None:
    if settings.require_consent and not (registration.consent and registration.consent.accepted):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Consent required: record the participant's acceptance of the verification notice before submitting",
        )


def _policy(store: Store, event_id: str, tenant: str) -> EventPolicy:
    if (policy := store.get_policy(event_id, tenant)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event policy not found")
    return policy


def _load(store: Store, verification_id: str, tenant: str) -> VerificationResult:
    if (result := store.get_verification(verification_id, tenant)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification not found")
    return result


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large")
    return data


def _sniff(data: bytes) -> str | None:
    return next((kind for magic, kind in MAGIC.items() if data.startswith(magic)), None)


__all__ = ["public", "router"]
