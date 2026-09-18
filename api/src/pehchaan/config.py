from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PEHCHAAN_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    # Comma-separated "key:tenant:role" entries; role is platform, reviewer or admin. A bare key is an admin
    # of tenant "default". Keys are hashed in memory at startup.
    api_keys: SecretStr = SecretStr("")
    rate_limit_per_minute: int = 120  # verification submissions per API key
    cors_origins: str = "http://localhost:5173"
    max_upload_bytes: int = 10 * 1024 * 1024
    public_base_url: str = "http://localhost:8000"

    # Storage and secrets. In dev/test, missing secrets are generated into data_dir.
    data_dir: Path = Path("data")
    data_key: SecretStr = SecretStr("")  # Fernet key for images, names and embeddings at rest
    id_hash_pepper: SecretStr = SecretStr("")  # HMAC key for ID-number hashes
    signing_key: SecretStr = SecretStr("")  # EC P-256 PEM: Pehchaan Passes and OpenID4VP request objects

    # Privacy
    require_consent: bool = True
    image_storage: Literal["review_only", "all", "none"] = "review_only"
    image_retention_days: int = 30
    pass_validity_days: int = 365

    # Throughput
    workers: int = 2  # concurrent verifications per process; scale out with processes, not threads
    queue_size: int = 200  # waiting verifications before returning 429
    sync_timeout_seconds: float = 20.0  # after this, a sync request is answered 202 and finishes async
    ocr_workers: int = 1

    # OCR
    ocr_provider: Literal["auto", "textract", "rapidocr", "none"] = "auto"
    textract_enabled: bool = False
    textract_queries: bool = True
    aws_region: str = "ap-south-1"

    # Models, certificates and registries
    models_dir: Path = Path("models")
    uidai_cert_path: Path = Path("certs")  # Secure QR: a certificate file or a directory of .cer/.pem files
    uidai_jwks_path: Path = Path("certs/uidai-jwks.json")  # Aadhaar App SD-JWT issuer keys
    verifier_client_id: str = "pehchaan-ovse"
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

    # Unit economics (list prices; override per deployment region and contract)
    usd_textract_detect_per_page: float = 0.0015
    usd_textract_queries_per_page: float = 0.015
    usd_compute_per_cpu_hour: float = 0.04
    usd_llm_per_summary: float = 0.0005
    manual_review_minutes: float = 3.0

    seed_demo: bool = True
    demo_samples_dir: Path = Path("demo-samples")
    web_dist: Path = Path("../web/dist")


@lru_cache
def get_settings() -> Settings:
    return Settings()
