from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from helpers import EVENT_DATE

from pehchaan.config import Settings
from pehchaan.domain.policy import EventPolicy
from pehchaan.main import create_app
from pehchaan.specimens import make_test_signing_key

API_KEY = "test-key"


@pytest.fixture
def policy() -> EventPolicy:
    return EventPolicy(event_id="evt_test", event_date=EVENT_DATE, min_age=18)


@pytest.fixture(scope="session")
def signing_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("certs")
    make_test_signing_key(directory)
    return directory


def make_client(data_dir: Path, cert_dir: Path, ocr: str = "none") -> TestClient:
    settings = Settings(
        env="test",
        api_keys=API_KEY,
        data_dir=data_dir,
        uidai_cert_path=cert_dir,
        ocr_provider=ocr,  # type: ignore[arg-type]
        seed_demo=True,
        web_dist=data_dir / "no-web",
    )
    return TestClient(create_app(settings))


@pytest.fixture
def client(tmp_path: Path, signing_dir: Path):
    with make_client(tmp_path, signing_dir) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def ocr_client(tmp_path_factory: pytest.TempPathFactory, signing_dir: Path):
    with make_client(tmp_path_factory.mktemp("data"), signing_dir, ocr="rapidocr") as test_client:
        yield test_client
