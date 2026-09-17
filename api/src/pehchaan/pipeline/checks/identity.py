from __future__ import annotations

from pehchaan.domain.models import CheckResult, CheckStatus, DocType, Finding
from pehchaan.institutions import InstitutionRegistry, email_matches_institution
from pehchaan.names import APPROVE_AT, REJECT_BELOW, name_score
from pehchaan.pipeline.checks.base import Check, finding
from pehchaan.pipeline.context import VerificationContext


class IdentityCheck(Check):
    """Does the document belong to the person who filled in the form?"""

    name = "identity"

    def __init__(self, institutions: InstitutionRegistry) -> None:
        self._institutions = institutions

    async def run(self, ctx: VerificationContext) -> CheckResult:
        fields, form = ctx.fields, ctx.payload.form
        if not fields.name:
            return self.result(CheckStatus.SKIPPED, note="no name read from the document")

        findings: list[Finding] = []
        score = name_score(form.name, fields.name)
        if ctx.qr is not None and ctx.qr_certificate is not None:
            score = max(score, name_score(form.name, ctx.qr.name))
        if score >= APPROVE_AT:
            findings.append(finding("NAME_MATCH"))
        elif score >= REJECT_BELOW:
            findings.append(finding("NAME_PARTIAL_MATCH", detail=f"similarity {score:.2f}"))
        else:
            findings.append(finding("NAME_MISMATCH"))

        dob_conflict = False
        if form.dob and fields.dob:
            dob_conflict = form.dob != fields.dob
        elif form.dob and fields.year_of_birth:
            dob_conflict = form.dob.year != fields.year_of_birth
        if dob_conflict:
            findings.append(finding("DOB_MISMATCH_FORM"))

        institution = fields.institution or form.institution
        if institution and email_matches_institution(form.email, institution):
            findings.append(
                finding("VERIFIED_COLLEGE_EMAIL" if form.email_verified else "EMAIL_DOMAIN_MATCHES_INSTITUTION")
            )
        if fields.doc_type is DocType.COLLEGE_ID and fields.institution and self._institutions.available:
            if not self._institutions.contains(fields.institution):
                findings.append(finding("INSTITUTION_NOT_RECOGNISED"))

        status = CheckStatus.PASS if score >= APPROVE_AT and not dob_conflict else CheckStatus.WARN
        return self.result(status, *findings, name_similarity=round(score, 3))
