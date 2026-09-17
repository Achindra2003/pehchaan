"""SQLite persistence: verifications, encrypted blobs, duplicate index, reviews and a hash-chained audit log.

Single-node for the hackathon; the schema maps one-to-one onto Postgres (+ pgvector for faces).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from pehchaan.domain.models import Decision, ReviewRecord, VerificationResult, VerificationSummary
from pehchaan.domain.policy import EventPolicy, EventRules
from pehchaan.security import Crypto

SCHEMA = """
CREATE TABLE IF NOT EXISTS policies (
    event_id TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (event_id, version)
);
CREATE TABLE IF NOT EXISTS verifications (
    id TEXT PRIMARY KEY, event_id TEXT NOT NULL, registration_id TEXT NOT NULL, idempotency_key TEXT UNIQUE,
    decision TEXT NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0, body TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS verifications_event ON verifications (event_id, created_at);
CREATE TABLE IF NOT EXISTS blobs (
    verification_id TEXT NOT NULL, kind TEXT NOT NULL, media_type TEXT NOT NULL, data BLOB NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (verification_id, kind)
);
CREATE TABLE IF NOT EXISTS identity_index (
    verification_id TEXT NOT NULL, event_id TEXT NOT NULL, registration_id TEXT NOT NULL,
    key_type TEXT NOT NULL, key TEXT NOT NULL, name_enc BLOB NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS identity_index_key ON identity_index (key_type, key);
CREATE TABLE IF NOT EXISTS face_index (
    verification_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, registration_id TEXT NOT NULL,
    id_hashes TEXT NOT NULL, embedding_enc BLOB NOT NULL, name_enc BLOB NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, event TEXT NOT NULL, verification_id TEXT,
    data TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
"""

GENESIS = "0" * 64


@dataclass(frozen=True)
class IndexMatch:
    verification_id: str
    event_id: str
    registration_id: str
    key_type: str
    name: str
    distance: float = 0.0


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

    # --- policies ------------------------------------------------------------------

    def put_policy(self, event_id: str, rules: EventRules) -> EventPolicy:
        with self._lock:
            row = self._db.execute("SELECT MAX(version) AS v FROM policies WHERE event_id = ?", (event_id,)).fetchone()
            policy = EventPolicy(**rules.model_dump(), event_id=event_id, version=(row["v"] or 0) + 1)
            self._db.execute(
                "INSERT INTO policies VALUES (?, ?, ?, ?)",
                (event_id, policy.version, policy.model_dump_json(), _now()),
            )
        self.audit("policy.updated", None, {"event_id": event_id, "version": policy.version})
        return policy

    def get_policy(self, event_id: str) -> EventPolicy | None:
        row = self._db.execute(
            "SELECT body FROM policies WHERE event_id = ? ORDER BY version DESC LIMIT 1", (event_id,)
        ).fetchone()
        return EventPolicy.model_validate_json(row["body"]) if row else None

    def list_policies(self) -> list[EventPolicy]:
        rows = self._db.execute(
            "SELECT body FROM policies p WHERE version = (SELECT MAX(version) FROM policies WHERE event_id = p.event_id)"
            " ORDER BY event_id"
        ).fetchall()
        return [EventPolicy.model_validate_json(r["body"]) for r in rows]

    # --- verifications ---------------------------------------------------------------

    def save_verification(self, result: VerificationResult, idempotency_key: str | None) -> None:
        now = _now()
        with self._lock:
            self._db.execute(
                "INSERT INTO verifications VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    result.verification_id, result.event_id, result.registration_id, idempotency_key,
                    result.decision.value, int(result.review is not None), result.model_dump_json(), now, now,
                ),
            )  # fmt: skip

    def update_verification(self, result: VerificationResult) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE verifications SET decision = ?, reviewed = ?, body = ?, updated_at = ? WHERE id = ?",
                (
                    result.decision.value, int(result.review is not None), result.model_dump_json(), _now(),
                    result.verification_id,
                ),
            )  # fmt: skip

    def get_verification(self, verification_id: str) -> VerificationResult | None:
        row = self._db.execute("SELECT body FROM verifications WHERE id = ?", (verification_id,)).fetchone()
        return VerificationResult.model_validate_json(row["body"]) if row else None

    def count_attempts(self, event_id: str, registration_id: str) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) AS n FROM verifications WHERE event_id = ? AND registration_id = ?",
            (event_id, registration_id),
        ).fetchone()
        return int(row["n"])

    def find_by_idempotency_key(self, key: str) -> VerificationResult | None:
        row = self._db.execute("SELECT body FROM verifications WHERE idempotency_key = ?", (key,)).fetchone()
        return VerificationResult.model_validate_json(row["body"]) if row else None

    def list_verifications(
        self, event_id: str | None = None, decision: Decision | None = None, open_only: bool = False, limit: int = 200
    ) -> list[VerificationSummary]:
        clauses, params = [], []
        if event_id:
            clauses.append("event_id = ?")
            params.append(event_id)
        if decision:
            clauses.append("decision = ?")
            params.append(decision.value)
        if open_only:
            clauses.append("decision = 'needs_review' AND reviewed = 0")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.execute(
            f"SELECT body FROM verifications {where} ORDER BY created_at DESC LIMIT ?",  # noqa: S608 - fixed clauses
            (*params, limit),
        ).fetchall()
        return [_summary(VerificationResult.model_validate_json(r["body"])) for r in rows]

    def stats(self, event_id: str | None = None) -> dict[str, Any]:
        where, params = ("WHERE event_id = ?", (event_id,)) if event_id else ("", ())
        rows = self._db.execute(
            f"SELECT decision, reviewed, body FROM verifications {where}",  # noqa: S608 - fixed clause
            params,
        ).fetchall()
        results = [VerificationResult.model_validate_json(r["body"]) for r in rows]
        by_decision: dict[str, int] = {d.value: 0 for d in Decision}
        by_automated: dict[str, int] = {d.value: 0 for d in Decision}
        for result in results:
            by_decision[result.decision.value] += 1
            by_automated[result.automated_decision.value] += 1
        latencies = sorted(r.latency_ms for r in results)
        total = len(results)
        return {
            "total": total,
            "by_decision": by_decision,
            "by_automated_decision": by_automated,
            "auto_verified_rate": round(by_automated["verified"] / total, 3) if total else None,
            "open_reviews": sum(1 for r in rows if r["decision"] == "needs_review" and not r["reviewed"]),
            "p50_latency_ms": latencies[total // 2] if total else None,
            "p95_latency_ms": latencies[min(total - 1, int(total * 0.95))] if total else None,
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
        )
        return result

    # --- encrypted blobs ---------------------------------------------------------------

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

    # --- duplicate index ------------------------------------------------------------------

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
        rows = self._db.execute("SELECT * FROM identity_index WHERE key_type = 'pdq'").fetchall()
        matches = []
        for r in rows:
            distance = (int(r["key"], 16) ^ target).bit_count()
            if distance <= max_distance and (r["event_id"], r["registration_id"]) != exclude:
                matches.append(self._match(r, "pdq", distance))
        return matches

    def find_similar_faces(
        self, embedding: np.ndarray, min_similarity: float, exclude: tuple[str, str]
    ) -> list[tuple[IndexMatch, list[str]]]:
        rows = self._db.execute("SELECT * FROM face_index").fetchall()
        matches = []
        for r in rows:
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

    # --- retention -------------------------------------------------------------------------

    def purge_expired(self, retention_days: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        with self._lock:
            blobs = self._db.execute("DELETE FROM blobs WHERE created_at < ?", (cutoff,)).rowcount
            faces = self._db.execute("DELETE FROM face_index WHERE created_at < ?", (cutoff,)).rowcount
        if blobs or faces:
            self.audit("retention.purged", None, {"blobs": blobs, "faces": faces, "cutoff": cutoff})
        return blobs + faces

    # --- audit log ---------------------------------------------------------------------------

    def audit(self, event: str, verification_id: str | None, data: dict[str, Any]) -> None:
        with self._lock:
            row = self._db.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row["hash"] if row else GENESIS
            at = _now()
            body = json.dumps(data, sort_keys=True, separators=(",", ":"))
            digest = _chain_hash(prev, at, event, verification_id, body)
            self._db.execute(
                "INSERT INTO audit_log (at, event, verification_id, data, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?)",
                (at, event, verification_id, body, prev, digest),
            )

    def audit_entries(self, verification_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        if verification_id:
            rows = self._db.execute(
                "SELECT * FROM audit_log WHERE verification_id = ? ORDER BY seq", (verification_id,)
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM audit_log ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows]

    def verify_audit_chain(self) -> dict[str, Any]:
        prev = GENESIS
        count = 0
        for row in self._db.execute("SELECT * FROM audit_log ORDER BY seq"):
            expected = _chain_hash(prev, row["at"], row["event"], row["verification_id"], row["data"])
            if row["prev_hash"] != prev or row["hash"] != expected:
                return {"intact": False, "entries": count, "broken_at_seq": row["seq"]}
            prev = row["hash"]
            count += 1
        return {"intact": True, "entries": count, "head": prev}


def _chain_hash(prev: str, at: str, event: str, verification_id: str | None, body: str) -> str:
    return hashlib.sha256("|".join((prev, at, event, verification_id or "", body)).encode()).hexdigest()


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
        reviewed=result.review is not None,
        top_reason=blocking[0].message if blocking else None,
        created_at=result.created_at,
    )
