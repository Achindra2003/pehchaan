from __future__ import annotations

import json

from conftest import API_KEY

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def auth(**extra: str) -> dict[str, str]:
    return {"X-API-Key": API_KEY, **extra}


def payload(event_id: str = "evt_1", **form: str) -> str:
    return json.dumps({"registration_id": "reg_1", "event_id": event_id, "form": {"name": "Asha Rao", **form}})


def test_healthz_is_public(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_v1_requires_api_key(client):
    assert client.get("/v1/events").status_code == 401


def test_demo_events_are_seeded(client):
    events = {e["event_id"] for e in client.get("/v1/events", headers=auth()).json()}
    assert {"ai-build-challenge-blr", "campus-hack-students", "junior-coders-13-17"} <= events


def test_policy_versions_increment(client):
    rules = {"event_date": "2026-09-18", "min_age": 18}
    assert client.put("/v1/events/evt_1/policy", json=rules, headers=auth()).json()["version"] == 1
    assert client.put("/v1/events/evt_1/policy", json=rules, headers=auth()).json()["version"] == 2


def test_unreadable_image_asks_for_retake_and_is_idempotent(client):
    client.put("/v1/events/evt_1/policy", json={"event_date": "2026-09-18"}, headers=auth())
    files = {"id_image": ("id.jpg", JPEG, "image/jpeg")}
    headers = auth(**{"Idempotency-Key": "reg_1-attempt-1"})

    first = client.post("/v1/verifications", data={"payload": payload()}, files=files, headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["decision"] == "action_required"
    assert body["actions"] == ["retake_id_photo"]

    again = client.post("/v1/verifications", data={"payload": payload()}, files=files, headers=headers)
    assert again.json()["verification_id"] == body["verification_id"]


def test_rejects_non_image_uploads(client):
    files = {"id_image": ("id.jpg", b"not an image", "image/jpeg")}
    response = client.post(
        "/v1/verifications", data={"payload": payload("ai-build-challenge-blr")}, files=files, headers=auth()
    )
    assert response.status_code == 415


def test_validation_errors_do_not_echo_personal_data(client):
    files = {"id_image": ("id.jpg", JPEG, "image/jpeg")}
    bad = payload("ai-build-challenge-blr", dob="31-31-2004")
    response = client.post("/v1/verifications", data={"payload": bad}, files=files, headers=auth())
    assert response.status_code == 422
    assert "31-31-2004" not in response.text


def test_review_overrides_decision_and_is_audited(client):
    files = {"id_image": ("id.jpg", JPEG, "image/jpeg")}
    created = client.post(
        "/v1/verifications", data={"payload": payload("ai-build-challenge-blr")}, files=files, headers=auth()
    ).json()
    vid = created["verification_id"]

    review = {"action": "approve", "reviewer": "organiser@hackingly", "note": "checked in person"}
    reviewed = client.post(f"/v1/verifications/{vid}/review", json=review, headers=auth()).json()
    assert reviewed["decision"] == "verified"
    assert reviewed["automated_decision"] == "action_required"

    events = [e["event"] for e in client.get(f"/v1/verifications/{vid}/audit", headers=auth()).json()]
    assert events == ["verification.created", "verification.reviewed"]
    assert client.get("/v1/audit/integrity", headers=auth()).json()["intact"]


def test_images_are_served_decrypted_to_authorised_callers_only(client):
    files = {"id_image": ("id.jpg", JPEG, "image/jpeg")}
    vid = client.post(
        "/v1/verifications", data={"payload": payload("ai-build-challenge-blr")}, files=files, headers=auth()
    ).json()["verification_id"]
    assert client.get(f"/v1/verifications/{vid}/images/id").status_code == 401
    image = client.get(f"/v1/verifications/{vid}/images/id", headers=auth())
    assert image.content == JPEG
    assert image.headers["cache-control"] == "no-store"


def test_copilot_falls_back_to_rules_without_llm(client):
    files = {"id_image": ("id.jpg", JPEG, "image/jpeg")}
    vid = client.post(
        "/v1/verifications", data={"payload": payload("ai-build-challenge-blr")}, files=files, headers=auth()
    ).json()["verification_id"]
    summary = client.get(f"/v1/verifications/{vid}/copilot", headers=auth()).json()
    assert summary["source"] == "rules"
    assert summary["suggested_action"] == "request_retake"
