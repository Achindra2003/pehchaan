from __future__ import annotations

from datetime import date

from pehchaan.domain.models import CheckResult, CheckStatus, DocType, FieldSource, Finding
from pehchaan.domain.policy import EventPolicy
from pehchaan.pipeline.checks.base import Check, finding
from pehchaan.pipeline.context import VerificationContext

CONFIDENT_OCR = 0.9


def age_on(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


class EligibilityCheck(Check):
    """Event rules: accepted documents, age on the event date, student status."""

    name = "eligibility"

    async def run(self, ctx: VerificationContext) -> CheckResult:
        policy, fields = ctx.policy, ctx.fields
        findings: list[Finding] = []

        if fields.doc_type is not DocType.UNKNOWN and fields.doc_type not in policy.accepted_documents:
            accepted = ", ".join(sorted(d.value.replace("_", " ") for d in policy.accepted_documents))
            findings.append(
                finding("DOC_TYPE_NOT_ACCEPTED", doc_type=fields.doc_type.value.replace("_", " "), accepted=accepted)
            )

        age, age_findings = self._age(ctx)
        findings += age_findings

        if policy.student_only:
            findings += self._student(ctx)

        blocking = {"AGE_BELOW_MIN_CONFIRMED", "AGE_ABOVE_MAX_CONFIRMED"}
        status = CheckStatus.FAIL if any(f.code in blocking for f in findings) else CheckStatus.PASS
        return self.result(status, *findings, age_on_event_date=age)

    def _age(self, ctx: VerificationContext) -> tuple[int | None, list[Finding]]:
        policy, fields = ctx.policy, ctx.fields
        has_age_rule = policy.min_age is not None or policy.max_age is not None

        if fields.dob is not None:
            age = age_on(fields.dob, policy.event_date)
            youngest = oldest = age
        elif fields.year_of_birth is not None:
            # Year-of-birth-only cards: the birthday may or may not have passed by the event.
            oldest = policy.event_date.year - fields.year_of_birth
            youngest = oldest - 1
            age = None
        else:
            return None, [finding("AGE_UNKNOWN")] if has_age_rule else []

        findings: list[Finding] = []
        if youngest < policy.guardian_consent_under:
            findings.append(finding("MINOR_GUARDIAN_CONSENT", under=policy.guardian_consent_under))

        if not has_age_rule:
            return age, findings

        youngest_ok, oldest_ok = self._within(youngest, policy), self._within(oldest, policy)
        if youngest_ok and oldest_ok:
            if age is not None:
                findings.append(finding("AGE_ELIGIBLE", age=age))
            return age, findings
        if youngest_ok or oldest_ok:
            findings.append(finding("AGE_BOUNDARY_UNCERTAIN"))
            return age, findings

        shown_age = age if age is not None else f"{youngest}-{oldest}"
        if not self._dob_confirmed(ctx):
            findings.append(finding("AGE_OUT_OF_RANGE_UNCONFIRMED", age=shown_age))
        elif policy.min_age is not None and oldest < policy.min_age:
            findings.append(finding("AGE_BELOW_MIN_CONFIRMED", age=shown_age, min_age=policy.min_age))
        else:
            findings.append(finding("AGE_ABOVE_MAX_CONFIRMED", age=shown_age, max_age=policy.max_age or ""))
        return age, findings

    def _student(self, ctx: VerificationContext) -> list[Finding]:
        fields = ctx.fields
        if fields.doc_type is not DocType.COLLEGE_ID:
            return [finding("STUDENT_PROOF_REQUIRED")]
        if fields.valid_until is None:
            return [finding("COLLEGE_ID_VALIDITY_UNKNOWN")]
        if fields.valid_until < ctx.policy.event_date:
            return [finding("COLLEGE_ID_EXPIRED", valid_until=fields.valid_until.isoformat())]
        return []

    @staticmethod
    def _within(age: int, policy: EventPolicy) -> bool:
        if policy.min_age is not None and age < policy.min_age:
            return False
        return not (policy.max_age is not None and age > policy.max_age)

    @staticmethod
    def _dob_confirmed(ctx: VerificationContext) -> bool:
        """A DOB is hard evidence only if it is UIDAI-signed, or read confidently AND matching the form."""
        fields = ctx.fields
        if fields.dob_source is FieldSource.QR_SIGNED:
            return True
        return (
            fields.dob_source is FieldSource.OCR
            and fields.confidence.get("dob", 0.0) >= CONFIDENT_OCR
            and ctx.payload.form.dob == fields.dob
        )
