from __future__ import annotations

from typing import TYPE_CHECKING

from pehchaan.pipeline.checks.aadhaar_qr import AadhaarQrCheck
from pehchaan.pipeline.checks.base import Check
from pehchaan.pipeline.checks.document_rules import DocumentRulesCheck
from pehchaan.pipeline.checks.duplicates import DuplicatesCheck
from pehchaan.pipeline.checks.eligibility import EligibilityCheck
from pehchaan.pipeline.checks.extract import ExtractCheck
from pehchaan.pipeline.checks.identity import IdentityCheck
from pehchaan.pipeline.checks.quality import QualityCheck
from pehchaan.pipeline.checks.selfie import SelfieCheck
from pehchaan.pipeline.checks.tamper import TamperCheck

if TYPE_CHECKING:
    from pehchaan.pipeline.engines import Engines


def build_checks(engines: Engines) -> dict[str, Check]:
    settings = engines.settings
    checks: list[Check] = [
        QualityCheck(engines.faces),
        ExtractCheck(
            engines.qr, engines.certificates, engines.textract, engines.rapid, use_queries=settings.textract_queries
        ),
        AadhaarQrCheck(engines.faces, certificates_available=engines.certificates.available),
        DocumentRulesCheck(),
        TamperCheck(recapture_enabled=settings.recapture_check_enabled),
        DuplicatesCheck(engines.store, engines.crypto, engines.faces),
        IdentityCheck(engines.institutions),
        SelfieCheck(engines.faces, settings.liveness_enabled, settings.liveness_threshold),
        EligibilityCheck(),
    ]
    return {check.name: check for check in checks}


__all__ = ["Check", "build_checks"]
