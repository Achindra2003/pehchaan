"""SQLite persistence: tenants' events and verifications, encrypted blobs, the duplicate index, passes,
Aadhaar App sessions, and a hash-chained audit log.

Single-node for the hackathon. Every table maps one-to-one onto Postgres (+ pgvector for faces, object storage
for blobs), which is the production deployment; see docs/ARCHITECTURE.md.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from pehchaan.domain.models import (
    Decision,
    EvidenceSource,
    ObservedOutcome,
    ReviewRecord,
    VerificationResult,
    VerificationSummary,
)
from pehchaan.domain.policy import EventPolicy, EventRules
from pehchaan.security import Crypto

SCHEMA = """
CREATE TABLE IF NOT EXISTS policies (
    event_id TEXT NOT NULL, version INTEGER NOT NULL, tenant TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (event_id, version)
);
CREATE TABLE IF NOT EXISTS verifications (
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, event_id TEXT NOT NULL, registration_id TEXT NOT NULL,
    idempotency_key TEXT, decision TEXT NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0, body TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE (tenant, idempotency_key)
);
CREATE INDEX IF NOT EXISTS verifications_tenant ON verifications (tenant, event_id, created_at);
CREATE INDEX IF NOT EXISTS verifications_registration ON verifications (event_id, registration_id);
CREATE TABLE IF NOT EXISTS blobs (
    verification_id TEXT NOT NULL, kind TEXT NOT NULL, media_type TEXT NOT NULL, data BLOB NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (verification_id, kind)
);
CREATE TABLE IF NOT EXISTS identity_index (
    verification_id TEXT NOT NULL, event_id TEXT NOT NULL, registration_id TEXT NOT NULL,
    key_type TEXT NOT NULL, key TEXT NOT NULL, name_enc BLOB NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS identity_index_key ON identity_index (key_type, key);
CREATE INDEX IF NOT EXISTS identity_index_verification ON identity_index (verification_id);
CREATE TABLE IF NOT EXISTS face_index (
    verification_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, registration_id TEXT NOT NULL,
    id_hashes TEXT NOT NULL, embedding_enc BLOB NOT NULL, name_enc BLOB NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS passes (
    pass_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, subject TEXT NOT NULL, verification_id TEXT NOT NULL,
    level INTEGER NOT NULL, issued_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT, revoked_reason TEXT
);
CREATE INDEX IF NOT EXISTS passes_verification ON passes (verification_id);
CREATE TABLE IF NOT EXISTS vc_sessions (
    session_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, nonce TEXT NOT NULL, request_enc BLOB NOT NULL,
    status TEXT NOT NULL, verification_id TEXT, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, tenant TEXT, event TEXT NOT NULL, verification_id TEXT,
    data TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
"""

GENESIS = "0" * 64


class TenantConflictError(PermissionError):
    pass


@dataclass(frozen=True)
class IndexMatch:
    verification_id: str
    event_id: str
    registration_id: str
    key_type: str
    name: str
    distance: float = 0.0


@dataclass(frozen=True)
class VcSession:
    session_id: str
    tenant: str
    nonce: str
    request: dict[str, Any]
    status: str
    verification_id: str | None
    expires_at: datetime


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path: Path, crypto: Crypto) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._crypto = crypto
        self._lock = threading.RLock()

    # --- policies ------------------------------------------------------------------------------

    def put_policy(self, tenant: str, event_id: str, rules: EventRules) -> EventPolicy:
        with self._lock:
            row = self._db.execute(
                "SELECT tenant, MAX(version) AS v FROM policies WHERE event_id = ?", (event_id,)
            ).fetchone()
            if row["v"] is not None and row["tenant"] != tenant:
                raise TenantConflictError(event_id)
            policy = EventPolicy(**rules.model_dump(), event_id=event_id, tenant=tenant, version=(row["v"] or 0) + 1)
            self._db.execute(
                "INSERT INTO policies VALUES (?, ?, ?, ?, ?)",
                (event_id, policy.version, tenant, policy.model_dump_json(), _now()),
            )
        self.audit("policy.updated", None, {"event_id": event_id, "version": policy.version}, tenant)
        return policy

    def get_policy(self, event_id: str, tenant: str | None = None) -> EventPolicy | None:
        row = self._db.execute(
            "SELECT body, tenant FROM policies WHERE event_id = ? ORDER BY version DESC LIMIT 1", (event_id,)
        ).fetchone()
        if row is None or (tenant is not None and row["tenant"] != tenant):
            return None
        return EventPolicy.model_validate_json(row["body"])

    def list_policies(self, tenant: str) -> list[EventPolicy]:
        rows = self._db.execute(
            "SELECT body FROM policies p WHERE tenant = ? AND version = "
            "(SELECT MAX(version) FROM policies WHERE event_id = p.event_id) ORDER BY event_id",
            (tenant,),
        ).fetchall()
        return [EventPolicy.model_validate_json(r["body"]) for r in rows]

    # --- verifications -----------------------------------------------------------------------------

    def save_verification(self, result: VerificationResult, tenant: str, idempotency_key: str | None) -> None:
        now = _now()
        with self._lock:
            self._db.execute(
                "INSERT INTO verifications VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    result.verification_id, tenant, result.event_id, result.registration_id, idempotency_key,
                    result.decision.value, int(result.review is not None), _body(result), now, now,
                ),
            )  # fmt: skip

    def update_verification(self, result: VerificationResult) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE verifications SET decision = ?, reviewed = ?, body = ?, updated_at = ? WHERE id = ?",
                (result.decision.value, int(result.review is not None), _body(result), _now(), result.verification_id),
            )

    def get_verification(self, verification_id: str, tenant: str | None = None) -> VerificationResult | None:
        row = self._db.execute("SELECT body, tenant FROM verifications WHERE id = ?", (verification_id,)).fetchone()
        if row is None or (tenant is not None and row["tenant"] != tenant):
            return None
        return VerificationResult.model_validate_json(row["body"])

    def tenant_of(self, verification_id: str) -> str | None:
        row = self._db.execute("SELECT tenant FROM verifications WHERE id = ?", (verification_id,)).fetchone()
        return row["tenant"] if row else None

    def find_by_idempotency_key(self, tenant: str, key: str) -> VerificationResult | None:
        row = self._db.execute(
            "SELECT body FROM verifications WHERE tenant = ? AND idempotency_key = ?", (tenant, key)
        ).fetchone()
        return VerificationResult.model_validate_json(row["body"]) if row else None

    def count_attempts(self, event_id: str, registration_id: str) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) AS n FROM verifications WHERE event_id = ? AND registration_id = ?",
            (event_id, registration_id),
        ).fetchone()
        return int(row["n"])

    def list_verifications(
        self,
        tenant: str,
        event_id: str | None = None,
        decision: Decision | None = None,
        open_only: bool = False,
        limit: int = 200,
    ) -> list[VerificationSummary]:
        clauses, params = ["tenant = ?"], [tenant]
        if event_id:
            clauses.append("event_id = ?")
            params.append(event_id)
        if decision:
            clauses.append("decision = ?")
            params.append(decision.value)
        if open_only:
            clauses.append("decision = 'needs_review' AND reviewed = 0")
        rows = self._db.execute(
            f"SELECT body FROM verifications WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?",  # noqa: S608 - fixed clauses
            (*params, limit),
        ).fetchall()
        summaries = [_summary(VerificationResult.model_validate_json(r["body"])) for r in rows]
        if open_only:
            summaries.sort(key=lambda s: s.priority, reverse=True)
        return summaries

    def _results(self, tenant: str, event_id: str | None) -> list[VerificationResult]:
        query, params = "SELECT body FROM verifications WHERE tenant = ?", [tenant]
        if event_id:
            query += " AND event_id = ?"
            params.append(event_id)
        return [VerificationResult.model_validate_json(r["body"]) for r in self._db.execute(query, params)]

    def stats(self, tenant: str, event_id: str | None = None) -> dict[str, Any]:
        results = self._results(tenant, event_id)
        total = len(results)
        latencies = sorted(r.latency_ms for r in results)
        automated = Counter(r.automated_decision.value for r in results)
        shadow = [r for r in results if r.observed_outcome is not None]
        return {
            "total": total,
            "by_decision": {d.value: sum(r.decision is d for r in results) for d in Decision},
            "by_automated_decision": {d.value: automated.get(d.value, 0) for d in Decision},
            "by_evidence_source": dict(Counter(r.evidence_source.value for r in results)),
            "auto_verified_rate": round(automated.get("verified", 0) / total, 3) if total else None,
            "open_reviews": sum(r.decision is Decision.NEEDS_REVIEW and r.review is None for r in results),
            "p50_latency_ms": latencies[total // 2] if total else None,
            "p95_latency_ms": latencies[min(total - 1, int(total * 0.95))] if total else None,
            "shadow_comparison": _shadow_comparison(shadow),
        }

    def usage(self, tenant: str, event_id: str | None, unit_review_minutes: float) -> dict[str, Any]:
        results = self._results(tenant, event_id)
        total = len(results)
        cost = sum(r.usage.estimated_cost_usd for r in results)
        human = sum(r.automated_decision is Decision.NEEDS_REVIEW for r in results)
        registrations_verified = len(
            {(r.event_id, r.registration_id) for r in results if r.decision is Decision.VERIFIED}
        )
        return {
            "verifications": total,
            "verified_registrations": registrations_verified,
            "by_evidence_source": dict(Counter(r.evidence_source.value for r in results)),
            "textract_pages": sum(r.usage.textract_detect_pages + r.usage.textract_query_pages for r in results),
            "compute_seconds": round(sum(r.usage.compute_ms for r in results) / 1000, 1),
            "estimated_cost_usd": round(cost, 4),
            "cost_per_verification_usd": round(cost / total, 5) if total else None,
            "sent_to_humans": human,
            "manual_review_minutes_avoided": round((total - human) * unit_review_minutes, 1),
            "passes_issued": self._db.execute(
                "SELECT COUNT(*) AS n FROM passes WHERE tenant = ?", (tenant,)
            ).fetchone()["n"],
        }

    def add_review(self, verification_id: str, review: ReviewRecord, decision: Decision) -> VerificationResult | None:
        with self._lock:
            result = self.get_verification(verification_id)
            if result is None:
                return None
            result = result.model_copy(update={"review": review, "decision": decision})
            self.update_verification(result)
        self.audit(
            "verification.reviewed",
            verification_id,
            {"action": review.action.value, "reviewer": review.reviewer, "decision": decision.value},
            self.tenant_of(verification_id),
        )
        return result

    def record_outcome(self, verification_id: str, outcome: ObservedOutcome) -> VerificationResult | None:
        with self._lock:
            result = self.get_verification(verification_id)
            if result is None:
                return None
            result = result.model_copy(update={"observed_outcome": outcome})
            self.update_verification(result)
        return result

    def erase(self, verification_id: str) -> VerificationResult | None:
        """Data principal erasure: remove images, embeddings and index entries; keep a minimal decision record."""
        with self._lock:
            result = self.get_verification(verification_id)
            if result is None:
                return None
            self._db.execute("DELETE FROM blobs WHERE verification_id = ?", (verification_id,))
            self._db.execute("DELETE FROM face_index WHERE verification_id = ?", (verification_id,))
            self._db.execute("DELETE FROM identity_index WHERE verification_id = ?", (verification_id,))
            redacted = result.model_copy(
                update={
                    "document": result.document.model_copy(update={"id_last4": None, "age_on_event_date": None}),
                    "checks": [c.model_copy(update={"details": {}}) for c in result.checks],
                    "reasons": [r.model_copy(update={"message": r.code}) for r in result.reasons],
                    "erased_at": datetime.now(UTC),
                }
            )
            self.update_verification(redacted)
            self.revoke_passes_for_verification(verification_id, "erased")
        self.audit("verification.erased", verification_id, {}, self.tenant_of(verification_id))
        return redacted

    # --- encrypted blobs ------------------------------------------------------------------------------

    def save_blob(self, verification_id: str, kind: str, media_type: str, data: bytes) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO blobs VALUES (?, ?, ?, ?, ?)",
                (verification_id, kind, media_type, self._crypto.encrypt(data), _now()),
            )

    def load_blob(self, verification_id: str, kind: str) -> tuple[str, bytes] | None:
        row = self._db.execute(
            "SELECT media_type, data FROM blobs WHERE verification_id = ? AND kind = ?", (verification_id, kind)
        ).fetchone()
        return (row["media_type"], self._crypto.decrypt(row["data"])) if row else None

    def delete_blobs(self, verification_id: str) -> int:
        with self._lock:
            return self._db.execute("DELETE FROM blobs WHERE verification_id = ?", (verification_id,)).rowcount

    # --- duplicate index --------------------------------------------------------------------------------

    def index_identity(
        self,
        verification_id: str,
        event_id: str,
        registration_id: str,
        name: str,
        keys: list[tuple[str, str]],
        face: np.ndarray | None,
        id_hashes: list[str],
    ) -> None:
        name_enc = self._crypto.encrypt(name.encode())
        now = _now()
        with self._lock:
            for key_type, key in keys:
                self._db.execute(
                    "INSERT INTO identity_index VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (verification_id, event_id, registration_id, key_type, key, name_enc, now),
                )
            if face is not None:
                self._db.execute(
                    "INSERT OR REPLACE INTO face_index VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        verification_id, event_id, registration_id, json.dumps(id_hashes),
                        self._crypto.encrypt(face.astype(np.float32).tobytes()), name_enc, now,
                    ),
                )  # fmt: skip

    def find_by_keys(self, key_type: str, keys: list[str], exclude: tuple[str, str]) -> list[IndexMatch]:
        if not keys:
            return []
        placeholders = ",".join("?" * len(keys))
        rows = self._db.execute(
            f"SELECT * FROM identity_index WHERE key_type = ? AND key IN ({placeholders})",  # noqa: S608
            (key_type, *keys),
        ).fetchall()
        return [self._match(r, key_type) for r in rows if (r["event_id"], r["registration_id"]) != exclude]

    def find_similar_images(self, pdq: str, max_distance: int, exclude: tuple[str, str]) -> list[IndexMatch]:
        target = int(pdq, 16)
        matches = []
        for r in self._db.execute("SELECT * FROM identity_index WHERE key_type = 'pdq'").fetchall():
            distance = (int(r["key"], 16) ^ target).bit_count()
            if distance <= max_distance and (r["event_id"], r["registration_id"]) != exclude:
                matches.append(self._match(r, "pdq", distance))
        return matches

    def find_similar_faces(
        self, embedding: np.ndarray, min_similarity: float, exclude: tuple[str, str]
    ) -> list[tuple[IndexMatch, list[str]]]:
        matches = []
        for r in self._db.execute("SELECT * FROM face_index").fetchall():
            if (r["event_id"], r["registration_id"]) == exclude:
                continue
            other = np.frombuffer(self._crypto.decrypt(r["embedding_enc"]), dtype=np.float32)
            similarity = float(np.dot(embedding, other))
            if similarity >= min_similarity:
                matches.append((self._match(r, "face", similarity), json.loads(r["id_hashes"])))
        return matches

    def _match(self, row: sqlite3.Row, key_type: str, distance: float = 0.0) -> IndexMatch:
        return IndexMatch(
            verification_id=row["verification_id"],
            event_id=row["event_id"],
            registration_id=row["registration_id"],
            key_type=key_type,
            name=self._crypto.decrypt(row["name_enc"]).decode(),
            distance=distance,
        )

    # --- passes -----------------------------------------------------------------------------------------------

    def record_pass(
        self, pass_id: str, tenant: str, subject: str, verification_id: str, level: int, expires_at: datetime
    ) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO passes VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
                (pass_id, tenant, subject, verification_id, level, _now(), expires_at.isoformat()),
            )
        self.audit("pass.issued", verification_id, {"pass_id": pass_id, "level": level}, tenant)

    def pass_revocation(self, pass_id: str) -> str | None:
        """None if the pass is known and active; the reason if revoked or unknown to this deployment."""
        row = self._db.execute("SELECT revoked_reason, revoked_at FROM passes WHERE pass_id = ?", (pass_id,)).fetchone()
        if row is None:
            return "unknown"
        return row["revoked_reason"] if row["revoked_at"] else None

    def revoke_pass(self, pass_id: str, tenant: str, reason: str) -> bool:
        with self._lock:
            updated = self._db.execute(
                "UPDATE passes SET revoked_at = ?, revoked_reason = ? WHERE pass_id = ? AND tenant = ? AND revoked_at IS NULL",
                (_now(), reason, pass_id, tenant),
            ).rowcount
        if updated:
            self.audit("pass.revoked", None, {"pass_id": pass_id, "reason": reason}, tenant)
        return bool(updated)

    def revoke_passes_for_verification(self, verification_id: str, reason: str) -> list[str]:
        rows = self._db.execute(
            "SELECT pass_id, tenant FROM passes WHERE verification_id = ? AND revoked_at IS NULL", (verification_id,)
        ).fetchall()
        return [r["pass_id"] for r in rows if self.revoke_pass(r["pass_id"], r["tenant"], reason)]

    # --- Aadhaar App sessions ----------------------------------------------------------------------------------

    def create_vc_session(
        self, session_id: str, tenant: str, nonce: str, request: dict[str, Any], ttl: timedelta
    ) -> None:
        now = datetime.now(UTC)
        with self._lock:
            self._db.execute(
                "INSERT INTO vc_sessions VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)",
                (
                    session_id, tenant, nonce, self._crypto.encrypt(json.dumps(request).encode()),
                    now.isoformat(), (now + ttl).isoformat(),
                ),
            )  # fmt: skip

    def get_vc_session(self, session_id: str) -> VcSession | None:
        row = self._db.execute("SELECT * FROM vc_sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return VcSession(
            session_id=row["session_id"],
            tenant=row["tenant"],
            nonce=row["nonce"],
            request=json.loads(self._crypto.decrypt(row["request_enc"])),
            status=row["status"],
            verification_id=row["verification_id"],
            expires_at=datetime.fromisoformat(row["expires_at"]),
        )

    def complete_vc_session(self, session_id: str, status: str, verification_id: str | None) -> bool:
        with self._lock:
            return bool(
                self._db.execute(
                    "UPDATE vc_sessions SET status = ?, verification_id = ? WHERE session_id = ? AND status = 'pending'",
                    (status, verification_id, session_id),
                ).rowcount
            )

    # --- retention ---------------------------------------------------------------------------------------------

    def purge_expired(self, retention_days: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        with self._lock:
            blobs = self._db.execute("DELETE FROM blobs WHERE created_at < ?", (cutoff,)).rowcount
            faces = self._db.execute("DELETE FROM face_index WHERE created_at < ?", (cutoff,)).rowcount
            sessions = self._db.execute("DELETE FROM vc_sessions WHERE expires_at < ?", (_now(),)).rowcount
        if blobs or faces:
            self.audit("retention.purged", None, {"blobs": blobs, "faces": faces, "cutoff": cutoff})
        return blobs + faces + sessions

    # --- audit log -----------------------------------------------------------------------------------------------

    def audit(self, event: str, verification_id: str | None, data: dict[str, Any], tenant: str | None = None) -> None:
        with self._lock:
            row = self._db.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row["hash"] if row else GENESIS
            at = _now()
            body = json.dumps(data, sort_keys=True, separators=(",", ":"))
            digest = _chain_hash(prev, at, tenant, event, verification_id, body)
            self._db.execute(
                "INSERT INTO audit_log (at, tenant, event, verification_id, data, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (at, tenant, event, verification_id, body, prev, digest),
            )

    def audit_entries(self, tenant: str, verification_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        if verification_id:
            rows = self._db.execute(
                "SELECT * FROM audit_log WHERE verification_id = ? AND tenant = ? ORDER BY seq",
                (verification_id, tenant),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM audit_log WHERE tenant = ? ORDER BY seq DESC LIMIT ?", (tenant, limit)
            ).fetchall()
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows]

    def verify_audit_chain(self) -> dict[str, Any]:
        prev = GENESIS
        count = 0
        for row in self._db.execute("SELECT * FROM audit_log ORDER BY seq"):
            expected = _chain_hash(prev, row["at"], row["tenant"], row["event"], row["verification_id"], row["data"])
            if row["prev_hash"] != prev or row["hash"] != expected:
                return {"intact": False, "entries": count, "broken_at_seq": row["seq"]}
            prev = row["hash"]
            count += 1
        return {"intact": True, "entries": count, "head": prev}


def _body(result: VerificationResult) -> str:
    return result.model_dump_json(exclude={"pehchaan_pass"})  # a pass token is returned once and never stored


def _chain_hash(prev: str, at: str, tenant: str | None, event: str, verification_id: str | None, body: str) -> str:
    return hashlib.sha256("|".join((prev, at, tenant or "", event, verification_id or "", body)).encode()).hexdigest()


def _priority(result: VerificationResult) -> int:
    if result.decision is not Decision.NEEDS_REVIEW or result.review is not None:
        return 0
    score = 50 + round((1 - result.confidence) * 20)
    if result.flags.duplicate_suspected:
        score += 30  # fraud rings affect more than one registration
    if result.flags.guardian_consent_required:
        score += 10
    return score


def _summary(result: VerificationResult) -> VerificationSummary:
    blocking = [r for r in result.reasons if r.effect.value in {"reject", "action", "review"}]
    return VerificationSummary(
        verification_id=result.verification_id,
        registration_id=result.registration_id,
        event_id=result.event_id,
        decision=result.decision,
        automated_decision=result.automated_decision,
        confidence=result.confidence,
        evidence_level=result.evidence_level,
        flags=result.flags,
        document=result.document,
        evidence_source=result.evidence_source,
        enforced=result.enforced,
        reviewed=result.review is not None,
        priority=_priority(result),
        top_reason=blocking[0].message if blocking else None,
        created_at=result.created_at,
    )


def _shadow_comparison(results: list[VerificationResult]) -> dict[str, Any] | None:
    """How Pehchaan's automated decisions compare with Hackingly's existing process, before enforcing."""
    if not results:
        return None
    agree = sum(r.automated_decision is r.observed_outcome.decision for r in results if r.observed_outcome)
    false_rejections = sum(
        r.automated_decision is Decision.NOT_ELIGIBLE and r.observed_outcome.decision is Decision.VERIFIED
        for r in results
        if r.observed_outcome
    )
    missed = sum(
        r.automated_decision is Decision.VERIFIED and r.observed_outcome.decision is Decision.NOT_ELIGIBLE
        for r in results
        if r.observed_outcome
    )
    return {
        "compared": len(results),
        "agreement_rate": round(agree / len(results), 3),
        "false_rejections": false_rejections,
        "fraud_missed": missed,
        "sent_to_review": sum(r.automated_decision is Decision.NEEDS_REVIEW for r in results),
    }


__all__ = ["EvidenceSource", "IndexMatch", "Store", "TenantConflictError", "VcSession"]
