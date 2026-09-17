from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PEHCHAAN_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    api_keys: SecretStr = SecretStr("")  # comma-separated
    id_hash_pepper: SecretStr = SecretStr("")
    max_upload_bytes: int = 10 * 1024 * 1024
    cors_origins: str = "http://localhost:5173"

    aws_region: str = "ap-south-1"
    textract_enabled: bool = False
    uidai_cert_path: Path = Path("certs/uidai_offline_publickey.cer")
    models_dir: Path = Path("models")
    llm_provider: Literal["none", "groq"] = "none"
    image_retention_days: int = 30

    @property
    def api_key_list(self) -> list[str]:
        return [key.strip() for key in self.api_keys.get_secret_value().split(",") if key.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
