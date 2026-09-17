from pehchaan.pipeline.checks.base import Check
from pehchaan.pipeline.checks.document_rules import DocumentRulesCheck
from pehchaan.pipeline.checks.eligibility import EligibilityCheck
from pehchaan.pipeline.checks.stubs import (
    AadhaarQrCheck,
    DuplicatesCheck,
    ExtractCheck,
    IdentityCheck,
    QualityCheck,
    SelfieCheck,
    TamperCheck,
)


def default_checks() -> dict[str, Check]:
    checks: list[Check] = [
        QualityCheck(),
        ExtractCheck(),
        DocumentRulesCheck(),
        AadhaarQrCheck(),
        TamperCheck(),
        DuplicatesCheck(),
        IdentityCheck(),
        SelfieCheck(),
        EligibilityCheck(),
    ]
    return {check.name: check for check in checks}


__all__ = ["Check", "default_checks"]
