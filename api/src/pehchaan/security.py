"""Secrets, encryption at rest, keyed hashing, API-key authentication, roles and rate limiting."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from pehchaan.config import Settings

logger = logging.getLogger(__name__)


class Crypto:
    def __init__(self, data_key: str, pepper: str, signing_key_pem: str) -> None:
        self._fernet = Fernet(data_key.encode())
        self._pepper = pepper.encode()
        key = serialization.load_pem_private_key(signing_key_pem.encode(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ValueError("signing key must be an EC P-256 private key")
        self.signing_key = key

    @classmethod
    def from_settings(cls, settings: Settings) -> Crypto:
        configured = (
            settings.data_key.get_secret_value(),
            settings.id_hash_pepper.get_secret_value(),
            settings.signing_key.get_secret_value(),
        )
        if all(configured):
            return cls(*configured)
        if settings.env == "prod":
            raise RuntimeError(
                "PEHCHAAN_DATA_KEY, PEHCHAAN_ID_HASH_PEPPER and PEHCHAAN_SIGNING_KEY are required in prod"
            )
        return cls(*_dev_secrets(settings.data_dir))

    def encrypt(self, data: bytes) -> bytes:
        return self._fernet.encrypt(data)

    def decrypt(self, token: bytes) -> bytes:
        return self._fernet.decrypt(token)

    def id_hash(self, value: str) -> str:
        return hmac.new(self._pepper, value.encode(), hashlib.sha256).hexdigest()


def _dev_secrets(data_dir: Path) -> tuple[str, str, str]:
    """Development only: persist generated secrets so encrypted data survives restarts."""
    path = data_dir / "dev-secrets.json"
    stored = json.loads(path.read_text()) if path.exists() else {}
    if not {"data_key", "pepper", "signing_key"} <= stored.keys():
        stored.setdefault("data_key", Fernet.generate_key().decode())
        stored.setdefault("pepper", secrets.token_urlsafe(32))
        stored.setdefault(
            "signing_key",
            ec.generate_private_key(ec.SECP256R1())
            .private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            .decode(),
        )
        data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stored))
        logger.warning("generated development secrets at %s; set real keys outside dev", path)
    return stored["data_key"], stored["pepper"], stored["signing_key"]


# --- API keys, tenants and roles -------------------------------------------------------------


class Role(StrEnum):
    PLATFORM = "platform"  # Hackingly's backend: submits verifications, reads results, manages its events
    REVIEWER = "reviewer"  # organiser staff: review queue, images, copilot
    ADMIN = "admin"  # everything within the tenant, including usage, erasure and pass revocation


class Permission(StrEnum):
    VERIFY = "verify"
    READ = "read"
    REVIEW = "review"
    VIEW_IMAGES = "view_images"
    MANAGE_EVENTS = "manage_events"
    ERASE = "erase"
    BILLING = "billing"
    AUDIT = "audit"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.PLATFORM: frozenset({Permission.VERIFY, Permission.READ, Permission.MANAGE_EVENTS, Permission.ERASE}),
    Role.REVIEWER: frozenset({Permission.READ, Permission.REVIEW, Permission.VIEW_IMAGES}),
    Role.ADMIN: frozenset(Permission),
}


@dataclass(frozen=True)
class Principal:
    tenant: str
    role: Role
    key_id: str

    def can(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS[self.role]


class KeyRing:
    """API keys are hashed on load; the plaintext is never kept in memory after startup."""

    def __init__(self, spec: str) -> None:
        self._keys: list[tuple[bytes, Principal]] = []
        for entry in filter(None, (part.strip() for part in spec.split(","))):
            key, tenant, role = ([*entry.split(":"), "", ""])[:3]
            digest = hashlib.sha256(key.encode()).digest()
            principal = Principal(tenant=tenant or "default", role=Role(role or "admin"), key_id=digest.hex()[:12])
            self._keys.append((digest, principal))

    @property
    def configured(self) -> bool:
        return bool(self._keys)

    def tenants(self) -> list[str]:
        return list(dict.fromkeys(principal.tenant for _, principal in self._keys))

    def authenticate(self, presented: str) -> Principal | None:
        digest = hashlib.sha256(presented.encode()).digest()
        match = None
        for stored, principal in self._keys:  # compare against every key to keep timing flat
            if hmac.compare_digest(stored, digest):
                match = principal
        return match


class RateLimiter:
    """Token bucket per API key. In production this lives in Redis so limits hold across replicas."""

    def __init__(self, per_minute: int) -> None:
        self._rate = per_minute / 60.0
        self._capacity = float(per_minute)
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key_id: str) -> tuple[bool, float]:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key_id, (self._capacity, now))
            tokens = min(self._capacity, tokens + (now - last) * self._rate)
            if tokens >= 1:
                self._buckets[key_id] = (tokens - 1, now)
                return True, 0.0
            self._buckets[key_id] = (tokens, now)
            return False, (1 - tokens) / self._rate
