from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from pehchaan.config import Settings, get_settings
from pehchaan.main import create_app

KEY = "test-key"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(env="test", api_keys=KEY)
    return TestClient(app)


def auth(**extra: str) -> dict[str, str]:
    return {"X-API-Key": KEY, **extra}


def payload() -> str:
    return json.dumps({"registration_id": "reg_1", "event_id": "evt_1", "form": {"name": "Asha Rao"}})


def test_healthz_is_public(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_v1_requires_api_key(client):
    assert client.get("/v1/events/evt_1/policy").status_code == 401


def test_policy_versions_increment(client):
    rules = {"event_date": "2026-09-18", "min_age": 18}
    assert client.put("/v1/events/evt_1/policy", json=rules, headers=auth()).json()["version"] == 1
    assert client.put("/v1/events/evt_1/policy", json=rules, headers=auth()).json()["version"] == 2


def test_verification_round_trip_is_idempotent(client):
    client.put("/v1/events/evt_1/policy", json={"event_date": "2026-09-18"}, headers=auth())
    files = {"id_image": ("id.jpg", JPEG, "image/jpeg")}
    headers = auth(**{"Idempotency-Key": "reg_1-attempt-1"})

    first = client.post("/v1/verifications", data={"payload": payload()}, files=files, headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["decision"] in {"verified", "needs_review", "action_required", "not_eligible"}
    assert {c["check"] for c in body["checks"]} >= {"quality", "extract", "eligibility"}

    again = client.post("/v1/verifications", data={"payload": payload()}, files=files, headers=headers)
    assert again.json()["verification_id"] == body["verification_id"]
    assert client.get(f"/v1/verifications/{body['verification_id']}", headers=auth()).status_code == 200


def test_rejects_non_image_uploads(client):
    client.put("/v1/events/evt_1/policy", json={"event_date": "2026-09-18"}, headers=auth())
    files = {"id_image": ("id.jpg", b"not an image", "image/jpeg")}
    response = client.post("/v1/verifications", data={"payload": payload()}, files=files, headers=auth())
    assert response.status_code == 415


def test_validation_errors_do_not_echo_personal_data(client):
    bad = json.dumps(
        {"registration_id": "reg_1", "event_id": "evt_1", "form": {"name": "Asha Rao", "dob": "31-31-2004"}}
    )
    files = {"id_image": ("id.jpg", JPEG, "image/jpeg")}
    response = client.post("/v1/verifications", data={"payload": bad}, files=files, headers=auth())
    assert response.status_code == 422
    assert "31-31-2004" not in response.text
