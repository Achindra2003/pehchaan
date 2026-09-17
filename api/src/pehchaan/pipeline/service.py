from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from time import perf_counter

from pehchaan.domain.decision import decide
from pehchaan.domain.models import (
    CheckStatus,
    Decision,
    DocumentSummary,
    Effect,
    Reason,
    VerificationPayload,
    VerificationResult,
)
from pehchaan.domain.policy import EventPolicy
from pehchaan.domain.reasons import CATALOG, render
from pehchaan.pipeline.checks import Check
from pehchaan.pipeline.context import VerificationContext
from pehchaan.pipeline.orchestrator import run_checks
from pehchaan.store.sqlite import Store
from pehchaan.webhooks import WebhookSender


class Verifier:
    def __init__(self, store: Store, checks: Mapping[str, Check], webhooks: WebhookSender) -> None:
        self._store = store
        self._checks = checks
        self._webhooks = webhooks

    @property
    def webhooks(self) -> WebhookSender:
        return self._webhooks

    async def verify(
        self,
        payload: VerificationPayload,
        policy: EventPolicy,
        id_image: bytes,
        id_media_type: str,
        selfie: bytes | None,
        idempotency_key: str | None,
    ) -> VerificationResult:
        started = perf_counter()
        ctx = VerificationContext(
            payload=payload,
            policy=policy,
            id_image=id_image,
            id_media_type=id_media_type,
            selfie=selfie,
            previous_attempts=self._store.count_attempts(payload.event_id, payload.registration_id),
        )
        results = await run_checks(ctx, self._checks)
        outcome = decide(results, policy)
        eligibility = ctx.results.get("eligibility")

        result = VerificationResult(
            verification_id=f"ver_{uuid.uuid4().hex}",
            registration_id=payload.registration_id,
            event_id=payload.event_id,
            decision=outcome.decision,
            automated_decision=outcome.decision,
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
            latency_ms=round((perf_counter() - started) * 1000),
            created_at=datetime.now(UTC),
        )

        self._store.save_verification(result, idempotency_key)
        self._store.save_blob(result.verification_id, "id", id_media_type, id_image)
        if selfie:
            self._store.save_blob(result.verification_id, "selfie", "image/jpeg", selfie)
        duplicates = ctx.results.get("duplicates")
        if duplicates is not None and duplicates.status is not CheckStatus.ERROR:
            keys = ctx.index_keys
            index_keys = [("id", h) for h in keys.id_hashes]
            if keys.pdq:
                index_keys.append(("pdq", keys.pdq))
            if keys.device_hash:
                index_keys.append(("device", keys.device_hash))
            self._store.index_identity(
                result.verification_id,
                payload.event_id,
                payload.registration_id,
                payload.form.name,
                index_keys,
                keys.face,
                keys.id_hashes,
            )
        self._store.audit(
            "verification.created",
            result.verification_id,
            {
                "event_id": result.event_id,
                "decision": result.decision.value,
                "level": int(result.evidence_level),
                "confidence": result.confidence,
                "reasons": [r.code for r in result.reasons],
                "policy": result.policy_version,
            },
        )
        self._webhooks.send("verification.completed", result)

        for other_id in ctx.conflicts:
            self._flag_conflict(other_id, result.verification_id)
        return result

    def _flag_conflict(self, verification_id: str, flagged_by: str) -> None:
        """Duplicates go to review on both sides: the earlier registration may be the impostor."""
        code = "DUPLICATE_LATER_REGISTRATION"
        other = self._store.get_verification(verification_id)
        if other is None or any(r.code == code for r in other.reasons):
            return
        reasons = [
            *other.reasons,
            Reason(code=code, effect=CATALOG[code].effect, check="duplicates", message=render(code, {})),
        ]
        update: dict[str, object] = {
            "reasons": reasons,
            "flags": other.flags.model_copy(update={"duplicate_suspected": True}),
        }
        if other.review is None and other.decision is Decision.VERIFIED:
            update["decision"] = Decision.NEEDS_REVIEW
        other = other.model_copy(update=update)
        self._store.update_verification(other)
        self._store.audit(
            "verification.flagged",
            verification_id,
            {"reason": code, "flagged_by": flagged_by, "decision": other.decision.value},
        )
        self._webhooks.send("verification.flagged", other)


__all__ = ["Effect", "Verifier"]
