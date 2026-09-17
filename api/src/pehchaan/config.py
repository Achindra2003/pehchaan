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
    cors_origins: str = "http://localhost:5173"
    max_upload_bytes: int = 10 * 1024 * 1024

    # Storage and secrets. In dev/test, missing secrets are generated into data_dir.
    data_dir: Path = Path("data")
    data_key: SecretStr = SecretStr("")  # Fernet key for images, names and embeddings at rest
    id_hash_pepper: SecretStr = SecretStr("")  # HMAC key for ID-number hashes
    image_retention_days: int = 30

    # OCR
    ocr_provider: Literal["auto", "textract", "rapidocr", "none"] = "auto"
    textract_enabled: bool = False
    textract_queries: bool = True
    aws_region: str = "ap-south-1"

    # Models and certificates
    models_dir: Path = Path("models")
    uidai_cert_path: Path = Path("certs")  # a certificate file or a directory of .cer/.pem files
    institutions_csv: Path = Path("data/aishe_colleges.csv")

    # Signals that need calibration on real samples before they may act
    recapture_check_enabled: bool = False
    liveness_enabled: bool = True
    liveness_threshold: float = 0.5

    # Reviewer copilot
    llm_provider: Literal["none", "groq"] = "none"
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "llama-3.3-70b-versatile"

    # Outbound webhooks to Hackingly
    webhook_url: str = ""
    webhook_secret: SecretStr = SecretStr("")

    seed_demo: bool = True
    web_dist: Path = Path("../web/dist")

    @property
    def api_key_list(self) -> list[str]:
        return [key.strip() for key in self.api_keys.get_secret_value().split(",") if key.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
