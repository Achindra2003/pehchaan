from __future__ import annotations

import re
from datetime import date

from stdnum.in_ import aadhaar, epic, pan

from pehchaan.domain.models import CheckResult, CheckStatus, DocType, Finding
from pehchaan.pipeline.checks.base import Check, finding
from pehchaan.pipeline.context import VerificationContext

MASKED_AADHAAR = re.compile(r"^[X*x]{8}\d{4}$")
PASSPORT = re.compile(r"^[A-Z][0-9]{7}$")
DRIVING_LICENCE = re.compile(r"^[A-Z]{2}[0-9]{2}[0-9]{4}[0-9]{7}$")


class DocumentRulesCheck(Check):
    """Deterministic format rules per document type. Never rejects on its own."""

    name = "document_rules"

    async def run(self, ctx: VerificationContext) -> CheckResult:
        fields = ctx.fields
        if fields.doc_type is DocType.UNKNOWN:
            return self.result(CheckStatus.SKIPPED, note="document type unknown")

        findings: list[Finding] = []
        number = re.sub(r"[\s-]", "", fields.id_number or "").upper()
        label = fields.doc_type.value.replace("_", " ")

        match fields.doc_type:
            case DocType.AADHAAR if MASKED_AADHAAR.match(number):
                findings.append(finding("ID_NUMBER_MASKED"))
            case DocType.AADHAAR:
                findings.append(self._format(aadhaar.is_valid(number), label))
            case DocType.PAN:
                findings.append(self._format(pan.is_valid(number), label))
                if pan.is_valid(number):
                    findings += self._pan_holder(number, f"{fields.name or ''} {ctx.payload.form.name}")
            case DocType.VOTER_ID:
                findings.append(self._format(epic.is_valid(number), label))
            case DocType.PASSPORT:
                findings.append(self._format(bool(PASSPORT.match(number)), label))
            case DocType.DRIVING_LICENCE:
                # State formats vary; a mismatch is only worth a confidence penalty.
                if DRIVING_LICENCE.match(number):
                    findings.append(finding("ID_NUMBER_VALID", doc_type=label))
            case DocType.COLLEGE_ID:
                pass

        if fields.dob is not None and not (date(1900, 1, 1) < fields.dob <= date.today()):
            findings.append(finding("DOB_IMPLAUSIBLE"))

        needs_review = any(f.code in {"ID_NUMBER_INVALID", "PAN_NOT_INDIVIDUAL", "DOB_IMPLAUSIBLE"} for f in findings)
        return self.result(CheckStatus.WARN if needs_review else CheckStatus.PASS, *findings)

    @staticmethod
    def _format(valid: bool, label: str) -> Finding:
        return finding("ID_NUMBER_VALID" if valid else "ID_NUMBER_INVALID", doc_type=label)

    @staticmethod
    def _pan_holder(number: str, name: str | None) -> list[Finding]:
        # 4th character is the holder type ('P' = individual); 5th is the surname initial,
        # which is unreliable for initial-first names, so it only lowers confidence.
        if number[3] != "P":
            return [finding("PAN_NOT_INDIVIDUAL")]
        initials = {token[0].upper() for token in re.findall(r"[A-Za-z]+", name or "")}
        if initials and number[4] not in initials:
            return [finding("PAN_SURNAME_INITIAL_MISMATCH")]
        return []
