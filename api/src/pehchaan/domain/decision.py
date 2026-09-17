"""Decision engine: a pure function of the evidence ledger and the event policy.

No model output reaches this module directly. Checks turn evidence into catalogued
findings; this module turns findings into a decision, so every outcome is replayable.
"""

from __future__ import annotations

from dataclasses import dataclass

from pehchaan.domain.models import (
    Action,
    CheckResult,
    CheckStatus,
    Decision,
    Effect,
    EvidenceLevel,
    Flags,
    Reason,
)
from pehchaan.domain.policy import EventPolicy
from pehchaan.domain.reasons import CATALOG, render

# Checks that must PASS for a level to be reached. Levels are cumulative.
LEVEL_REQUIREMENTS: tuple[tuple[EvidenceLevel, frozenset[str]], ...] = (
    (EvidenceLevel.READ, frozenset({"extract"})),
    (EvidenceLevel.CONSISTENT, frozenset({"document_rules", "identity"})),
    (EvidenceLevel.PROVEN, frozenset({"aadhaar_qr"})),
    (EvidenceLevel.PRESENT, frozenset({"selfie"})),
)

VERIFIED_BASE = {
    EvidenceLevel.CONSISTENT: 0.85,
    EvidenceLevel.PROVEN: 0.95,
    EvidenceLevel.PRESENT: 0.98,
}


@dataclass(frozen=True)
class Outcome:
    decision: Decision
    confidence: float
    level: EvidenceLevel
    reasons: list[Reason]
    actions: list[Action]
    flags: Flags


def evidence_level(results: dict[str, CheckResult]) -> EvidenceLevel:
    quality = results.get("quality")
    if quality is not None and quality.status is CheckStatus.FAIL:
        return EvidenceLevel.UNUSABLE
    level = EvidenceLevel.UNUSABLE
    for candidate, required in LEVEL_REQUIREMENTS:
        if all(_passed(results, name) for name in required):
            level = candidate
        else:
            break
    return level


def decide(results: list[CheckResult], policy: EventPolicy) -> Outcome:
    by_name = {r.check: r for r in results}
    level = evidence_level(by_name)
    reasons = _collect_reasons(results)

    effects = {r.effect for r in reasons}
    if level < policy.auto_verify_min_level and not effects & {Effect.REJECT, Effect.ACTION}:
        reasons.append(_reason("LEVEL_BELOW_EVENT_MINIMUM", "engine", {}))
        effects.add(Effect.REVIEW)

    flags = Flags()
    for reason in reasons:
        flag = CATALOG[reason.code].flag
        if flag:
            setattr(flags, flag, True)
    flags.minor = flags.guardian_consent_required

    actions = list(dict.fromkeys(a for r in reasons if (a := CATALOG[r.code].action)))
    penalties = sum(1 for r in reasons if r.effect is Effect.PENALTY)
    review_count = sum(1 for r in reasons if r.effect is Effect.REVIEW)

    if Effect.REJECT in effects:
        decision = Decision.NOT_ELIGIBLE
        confidence = max(CATALOG[r.code].strength for r in reasons if r.effect is Effect.REJECT)
        actions = []
    elif Effect.ACTION in effects:
        decision = Decision.ACTION_REQUIRED
        confidence = 0.9
    elif Effect.REVIEW in effects:
        decision = Decision.NEEDS_REVIEW
        confidence = _clamp(0.4 + 0.1 * level - 0.05 * (review_count - 1) - 0.03 * penalties, 0.2, 0.7)
    else:
        decision = Decision.VERIFIED
        confidence = VERIFIED_BASE.get(level, 0.8) - 0.03 * penalties
        if level < EvidenceLevel.PROVEN and _passed(by_name, "selfie"):
            confidence += 0.04
        confidence = _clamp(confidence, 0.5, 0.99)

    return Outcome(
        decision=decision,
        confidence=round(confidence, 2),
        level=level,
        reasons=reasons,
        actions=actions,
        flags=flags,
    )


def _collect_reasons(results: list[CheckResult]) -> list[Reason]:
    reasons: list[Reason] = []
    for result in results:
        if result.status is CheckStatus.ERROR:
            reasons.append(_reason("CHECK_ERROR", result.check, {"check": result.check}))
        for finding in result.findings:
            reasons.append(_reason(finding.code, result.check, finding.params))
    return reasons


def _reason(code: str, check: str, params: dict[str, str | int | float]) -> Reason:
    return Reason(code=code, effect=CATALOG[code].effect, check=check, message=render(code, params))


def _passed(results: dict[str, CheckResult], name: str) -> bool:
    result = results.get(name)
    return result is not None and result.status is CheckStatus.PASS


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
