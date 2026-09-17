"""In-memory store for the walking skeleton. Stream A replaces it with SQLite/Postgres."""

from __future__ import annotations

from pehchaan.domain.models import VerificationResult
from pehchaan.domain.policy import EventPolicy, EventRules


class MemoryStore:
    def __init__(self) -> None:
        self._policies: dict[str, EventPolicy] = {}
        self._verifications: dict[str, VerificationResult] = {}
        self._by_idempotency_key: dict[str, str] = {}

    def put_policy(self, event_id: str, rules: EventRules) -> EventPolicy:
        current = self._policies.get(event_id)
        policy = EventPolicy(**rules.model_dump(), event_id=event_id, version=current.version + 1 if current else 1)
        self._policies[event_id] = policy
        return policy

    def get_policy(self, event_id: str) -> EventPolicy | None:
        return self._policies.get(event_id)

    def save_verification(self, result: VerificationResult, idempotency_key: str | None) -> None:
        self._verifications[result.verification_id] = result
        if idempotency_key:
            self._by_idempotency_key[idempotency_key] = result.verification_id

    def get_verification(self, verification_id: str) -> VerificationResult | None:
        return self._verifications.get(verification_id)

    def find_by_idempotency_key(self, key: str) -> VerificationResult | None:
        verification_id = self._by_idempotency_key.get(key)
        return self._verifications.get(verification_id) if verification_id else None
