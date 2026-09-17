from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pehchaan.domain.models import CheckResult, CheckStatus, Finding
from pehchaan.pipeline.context import VerificationContext


class Check(ABC):
    """One independent piece of evidence.

    Rules for implementers:
    - Emit only codes listed in `domain/reasons.py`.
    - Never put raw ID numbers, names or images in `details`; they are persisted.
    - Run CPU-heavy work with `asyncio.to_thread` so checks stay parallel.
    - Uncertainty is REVIEW, not FAIL. FAIL means the check has hard evidence.
    """

    name: ClassVar[str]

    @abstractmethod
    async def run(self, ctx: VerificationContext) -> CheckResult: ...

    def result(self, status: CheckStatus, *findings: Finding, **details: object) -> CheckResult:
        return CheckResult(check=self.name, status=status, findings=list(findings), details=details)

    def not_implemented(self) -> CheckResult:
        return self.result(CheckStatus.SKIPPED, note="not implemented yet")


def finding(code: str, **params: str | int | float) -> Finding:
    return Finding(code=code, params=params)
