from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from time import perf_counter

from pehchaan.domain.models import CheckResult, CheckStatus
from pehchaan.pipeline.checks import Check
from pehchaan.pipeline.context import VerificationContext

logger = logging.getLogger(__name__)

# Checks within a stage run concurrently; stages run in order.
STAGES: tuple[tuple[str, ...], ...] = (
    ("quality",),
    ("extract",),
    ("aadhaar_qr",),  # may upgrade dob_source to QR_SIGNED, so it runs before the rest
    ("document_rules", "tamper", "duplicates", "identity", "selfie"),
    ("eligibility",),
)


async def run_checks(ctx: VerificationContext, checks: Mapping[str, Check]) -> list[CheckResult]:
    for stage in STAGES:
        results = await asyncio.gather(*(_run_one(checks[name], ctx) for name in stage if name in checks))
        for result in results:
            ctx.results[result.check] = result
        quality = ctx.results.get("quality")
        if quality is not None and quality.status is CheckStatus.FAIL:
            break  # unusable image: don't spend OCR on it
    return list(ctx.results.values())


async def _run_one(check: Check, ctx: VerificationContext) -> CheckResult:
    started = perf_counter()
    try:
        result = await check.run(ctx)
    except Exception as exc:
        # Exception messages can contain document data, so the full trace is debug-only.
        logger.error("check %s crashed: %s", check.name, type(exc).__name__)
        logger.debug("check %s traceback", check.name, exc_info=True)
        result = CheckResult(check=check.name, status=CheckStatus.ERROR)
    result.duration_ms = round((perf_counter() - started) * 1000)
    return result
