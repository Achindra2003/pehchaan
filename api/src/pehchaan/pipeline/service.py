from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from pehchaan.domain.decision import decide
from pehchaan.domain.models import DocumentSummary, VerificationPayload, VerificationResult
from pehchaan.domain.policy import EventPolicy
from pehchaan.pipeline.checks import Check
from pehchaan.pipeline.context import VerificationContext
from pehchaan.pipeline.orchestrator import run_checks


async def verify(
    payload: VerificationPayload,
    policy: EventPolicy,
    id_image: bytes,
    id_media_type: str,
    selfie: bytes | None,
    checks: Mapping[str, Check],
) -> VerificationResult:
    ctx = VerificationContext(
        payload=payload,
        policy=policy,
        id_image=id_image,
        id_media_type=id_media_type,
        selfie=selfie,
    )
    results = await run_checks(ctx, checks)
    outcome = decide(results, policy)
    eligibility = ctx.results.get("eligibility")

    return VerificationResult(
        verification_id=f"ver_{uuid.uuid4().hex}",
        registration_id=payload.registration_id,
        event_id=payload.event_id,
        decision=outcome.decision,
        confidence=outcome.confidence,
        evidence_level=outcome.level,
        reasons=outcome.reasons,
        actions=outcome.actions,
        flags=outcome.flags,
        document=DocumentSummary(
            type=ctx.fields.doc_type,
            id_last4=ctx.fields.id_last4,
            age_on_event_date=eligibility.details.get("age_on_event_date") if eligibility else None,
        ),
        policy_version=policy.version_tag,
        checks=results,
        created_at=datetime.now(UTC),
    )
