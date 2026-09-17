"""Verification service: three ways in (document, Pehchaan Pass, Aadhaar App), one way out."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from time import perf_counter

from pehchaan.aadhaar.app_vc import AadhaarAppClaims
from pehchaan.config import Settings
from pehchaan.domain.decision import decide
from pehchaan.domain.models import (
    CheckResult,
    CheckStatus,
    Decision,
    DocType,
    DocumentSummary,
    EvidenceLevel,
    EvidenceSource,
    ExtractedFields,
    FieldSource,
    PassIssued,
    PassVerificationRequest,
    Reason,
    Usage,
    VerificationPayload,
    VerificationResult,
)
from pehchaan.domain.policy import EventPolicy
from pehchaan.domain.reasons import CATALOG, render
from pehchaan.passes import PassAuthority, PassError
from pehchaan.pipeline.checks import Check
from pehchaan.pipeline.checks.base import finding
from pehchaan.pipeline.context import VerificationContext
from pehchaan.pipeline.orchestrator import run_checks
from pehchaan.store.sqlite import Store
from pehchaan.webhooks import WebhookSender


class Verifier:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        checks: Mapping[str, Check],
        passes: PassAuthority,
        webhooks: WebhookSender,
    ) -> None:
        self._settings = settings
        self._store = store
        self._checks = checks
        self._passes = passes
        self._webhooks = webhooks

    @property
    def webhooks(self) -> WebhookSender:
        return self._webhooks

    # --- ways in -----------------------------------------------------------------------------------------

    async def verify_document(
        self,
        tenant: str,
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
        return self._finalise(
            tenant, ctx, results, EvidenceSource.DOCUMENT, idempotency_key, started, images={"id": (id_media_type, id_image)} | ({"selfie": ("image/jpeg", selfie)} if selfie else {})
        )  # fmt: skip

    async def verify_pass(
        self, tenant: str, request: PassVerificationRequest, policy: EventPolicy, idempotency_key: str | None
    ) -> VerificationResult:
        started = perf_counter()
        payload = VerificationPayload(**request.model_dump(exclude={"pass_token"}))
        ctx = VerificationContext(payload=payload, policy=policy, id_image=b"", id_media_type="")
        pass_check = self._check_pass(ctx, request, tenant)
        results = [pass_check]
        if pass_check.status is CheckStatus.PASS:
            for name in ("identity", "eligibility"):
                results.append(await self._checks[name].run(ctx))
        return self._finalise(tenant, ctx, results, EvidenceSource.PASS, idempotency_key, started, images={})

    async def verify_aadhaar_app(
        self,
        tenant: str,
        payload: VerificationPayload,
        policy: EventPolicy,
        claims: AadhaarAppClaims | None,
        error: str | None,
    ) -> VerificationResult:
        started = perf_counter()
        ctx = VerificationContext(payload=payload, policy=policy, id_image=b"", id_media_type="")
        if claims is None:
            results = [
                CheckResult(check="aadhaar_app", status=CheckStatus.FAIL, findings=[finding("AADHAAR_APP_INVALID")], details={"error": error})
            ]  # fmt: skip
            return self._finalise(tenant, ctx, results, EvidenceSource.AADHAAR_APP, None, started, images={})

        ctx.fields = ExtractedFields(
            doc_type=DocType.AADHAAR,
            name=claims.name,
            dob=claims.dob,
            gender=claims.gender,
            id_number=claims.masked_uid,
            dob_source=FieldSource.AADHAAR_VC if claims.dob else None,
            age_attestations=claims.age_above,
        )
        needed = [c for c in _needed_claims(policy) if not _has_claim(claims, c)]
        if needed:
            app = CheckResult(
                check="aadhaar_app", status=CheckStatus.FAIL, findings=[finding("AADHAAR_APP_CLAIM_MISSING", claims=", ".join(needed))]
            )  # fmt: skip
        else:
            # The Aadhaar App authenticates the resident's face before sharing, so this is presence, not just proof.
            level = EvidenceLevel.PRESENT if claims.key_bound else EvidenceLevel.PROVEN
            app = CheckResult(
                check="aadhaar_app",
                status=CheckStatus.PASS,
                findings=[finding("AADHAAR_APP_VERIFIED")],
                details={"grants_level": int(level), "issuer": claims.issuer, "key_bound": claims.key_bound},
            )
        results = [app]
        for name in ("identity", "eligibility"):
            results.append(await self._checks[name].run(ctx))
        return self._finalise(tenant, ctx, results, EvidenceSource.AADHAAR_APP, None, started, images={})

    # --- one way out ---------------------------------------------------------------------------------------

    def _finalise(
        self,
        tenant: str,
        ctx: VerificationContext,
        results: list[CheckResult],
        source: EvidenceSource,
        idempotency_key: str | None,
        started: float,
        images: dict[str, tuple[str, bytes | None]],
    ) -> VerificationResult:
        payload, policy = ctx.payload, ctx.policy
        outcome = decide(results, policy)
        eligibility = ctx.results.get("eligibility") or next((r for r in results if r.check == "eligibility"), None)
        latency_ms = round((perf_counter() - started) * 1000)
        enforced = policy.mode == "enforce"

        result = VerificationResult(
            verification_id=f"ver_{uuid.uuid4().hex}",
            registration_id=payload.registration_id,
            event_id=payload.event_id,
            decision=outcome.decision,
            automated_decision=outcome.decision,
            enforced=enforced,
            confidence=outcome.confidence,
            evidence_level=outcome.level,
            evidence_source=source,
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
            consent_notice=payload.consent.notice_version if payload.consent else None,
            usage=self._usage(results, latency_ms),
            latency_ms=latency_ms,
            created_at=datetime.now(UTC),
        )

        self._store.save_verification(result, tenant, idempotency_key)
        if self._keep_images(result):
            for kind, (media_type, data) in images.items():
                if data:
                    self._store.save_blob(result.verification_id, kind, media_type, data)
        self._index(ctx, result)
        self._store.audit(
            "verification.created",
            result.verification_id,
            {
                "event_id": result.event_id,
                "source": source.value,
                "decision": result.decision.value,
                "enforced": enforced,
                "level": int(result.evidence_level),
                "confidence": result.confidence,
                "reasons": [r.code for r in result.reasons],
                "policy": result.policy_version,
                "consent_notice": result.consent_notice,
            },
            tenant,
        )

        issued = self._maybe_issue_pass(tenant, ctx, result, source)
        self._webhooks.send("verification.completed" if enforced else "verification.shadow_completed", result)
        for other_id in ctx.conflicts:
            self._flag_conflict(other_id, result.verification_id)
        return result.model_copy(update={"pehchaan_pass": issued}) if issued else result

    def _usage(self, results: list[CheckResult], latency_ms: int) -> Usage:
        extract = next((r for r in results if r.check == "extract"), None)
        details = extract.details if extract else {}
        s = self._settings
        detect, queries = int(details.get("textract_detect_pages", 0)), int(details.get("textract_query_pages", 0))
        cost = detect * s.usd_textract_detect_per_page + queries * s.usd_textract_queries_per_page
        cost += latency_ms / 3_600_000 * s.usd_compute_per_cpu_hour
        return Usage(
            ocr_provider=details.get("provider"),
            textract_detect_pages=detect,
            textract_query_pages=queries,
            compute_ms=latency_ms,
            estimated_cost_usd=round(cost, 6),
        )

    def _keep_images(self, result: VerificationResult) -> bool:
        mode = self._settings.image_storage
        return mode == "all" or (mode == "review_only" and result.decision is Decision.NEEDS_REVIEW)

    def _index(self, ctx: VerificationContext, result: VerificationResult) -> None:
        duplicates = ctx.results.get("duplicates")
        if duplicates is None or duplicates.status is CheckStatus.ERROR:
            return
        keys = ctx.index_keys
        index_keys = [("id", h) for h in keys.id_hashes]
        if keys.pdq:
            index_keys.append(("pdq", keys.pdq))
        if keys.device_hash:
            index_keys.append(("device", keys.device_hash))
        self._store.index_identity(
            result.verification_id,
            ctx.payload.event_id,
            ctx.payload.registration_id,
            ctx.payload.form.name,
            index_keys,
            keys.face,
            keys.id_hashes,
        )

    # --- Pehchaan Pass -----------------------------------------------------------------------------------------

    def _maybe_issue_pass(
        self, tenant: str, ctx: VerificationContext, result: VerificationResult, source: EvidenceSource
    ) -> PassIssued | None:
        subject = ctx.payload.subject_id
        if (
            not subject
            or source is EvidenceSource.PASS
            or not ctx.policy.issue_passes
            or result.decision is not Decision.VERIFIED
            or result.evidence_level < EvidenceLevel.CONSISTENT
            or result.flags.duplicate_suspected
        ):
            return None
        token, claims = self._passes.issue(result, ctx.fields, ctx.payload.form.name, tenant, subject)
        self._store.record_pass(
            claims.pass_id, tenant, claims.subject, result.verification_id, int(claims.level), claims.expires_at
        )
        return PassIssued(pass_id=claims.pass_id, token=token, level=claims.level, expires_at=claims.expires_at)

    def _check_pass(self, ctx: VerificationContext, request: PassVerificationRequest, tenant: str) -> CheckResult:
        def fail(code: str, status: CheckStatus = CheckStatus.FAIL) -> CheckResult:
            return CheckResult(check="pass", status=status, findings=[finding(code)])

        if not ctx.policy.accept_passes:
            return fail("PASS_NOT_ACCEPTED")
        try:
            claims = self._passes.verify(request.pass_token, tenant, request.subject_id or "")
        except PassError as exc:
            return fail(exc.code, CheckStatus.WARN if exc.code == "PASS_SUBJECT_MISMATCH" else CheckStatus.FAIL)
        if self._store.pass_revocation(claims.pass_id) is not None:
            return fail("PASS_REVOKED", CheckStatus.WARN)
        if claims.level < ctx.policy.auto_verify_min_level:
            return fail("PASS_LEVEL_TOO_LOW")

        ctx.fields = ExtractedFields(
            doc_type=DocType.COLLEGE_ID if claims.student_until else claims.doc_type,
            name=claims.name,
            dob=claims.dob,
            year_of_birth=claims.year_of_birth,
            valid_until=claims.student_until,
            dob_source=FieldSource.QR_SIGNED if claims.dob_confirmed else FieldSource.OCR,
            confidence={"dob": 1.0},
        )
        return CheckResult(
            check="pass",
            status=CheckStatus.PASS,
            findings=[finding("PASS_ACCEPTED", level=int(claims.level))],
            details={
                "grants_level": int(claims.level),
                "pass_id": claims.pass_id,
                "issued_from": claims.verification_id,
            },
        )

    # --- duplicates found later ----------------------------------------------------------------------------------

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
        revoked = self._store.revoke_passes_for_verification(verification_id, "duplicate identity found")
        self._store.audit(
            "verification.flagged",
            verification_id,
            {"reason": code, "flagged_by": flagged_by, "decision": other.decision.value, "passes_revoked": revoked},
            self._store.tenant_of(verification_id),
        )
        self._webhooks.send("verification.flagged", other)


def _needed_claims(policy: EventPolicy) -> list[str]:
    needed = ["ResidentName"]
    if policy.min_age is not None or policy.max_age is not None:
        needed.append("Dob or AgeAbove18" if policy.min_age == 18 and policy.max_age is None else "Dob")
    return needed


def _has_claim(claims: AadhaarAppClaims, needed: str) -> bool:
    if needed == "ResidentName":
        return bool(claims.name)
    if needed == "Dob":
        return claims.dob is not None
    return claims.dob is not None or 18 in claims.age_above
