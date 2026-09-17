"""Encryption at rest and keyed hashing of identity numbers."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

from pehchaan.config import Settings

logger = logging.getLogger(__name__)


class Crypto:
    def __init__(self, data_key: str, pepper: str) -> None:
        self._fernet = Fernet(data_key.encode())
        self._pepper = pepper.encode()

    @classmethod
    def from_settings(cls, settings: Settings) -> Crypto:
        data_key = settings.data_key.get_secret_value()
        pepper = settings.id_hash_pepper.get_secret_value()
        if data_key and pepper:
            return cls(data_key, pepper)
        if settings.env == "prod":
            raise RuntimeError("PEHCHAAN_DATA_KEY and PEHCHAAN_ID_HASH_PEPPER are required in prod")
        return cls(*_dev_secrets(settings.data_dir))

    def encrypt(self, data: bytes) -> bytes:
        return self._fernet.encrypt(data)

    def decrypt(self, token: bytes) -> bytes:
        return self._fernet.decrypt(token)

    def id_hash(self, value: str) -> str:
        return hmac.new(self._pepper, value.encode(), hashlib.sha256).hexdigest()


def _dev_secrets(data_dir: Path) -> tuple[str, str]:
    """Development only: persist generated secrets so encrypted data survives restarts."""
    path = data_dir / "dev-secrets.json"
    if path.exists():
        stored = json.loads(path.read_text())
        return stored["data_key"], stored["pepper"]
    data_dir.mkdir(parents=True, exist_ok=True)
    stored = {"data_key": Fernet.generate_key().decode(), "pepper": secrets.token_urlsafe(32)}
    path.write_text(json.dumps(stored))
    logger.warning("generated development secrets at %s; set real keys outside dev", path)
    return stored["data_key"], stored["pepper"]
