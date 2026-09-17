from __future__ import annotations

import json

from conftest import API_KEY, PLATFORM_KEY, REVIEWER_KEY, RIVAL_KEY
from helpers import CONSENT

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
EVENT = "ai-build-challenge-blr"


def auth(key: str = API_KEY, **extra: str) -> dict[str, str]:
    return {"X-API-Key": key, **extra}


def payload(event_id: str = EVENT, consent: dict | None = CONSENT, **form: str) -> str:
    body = {"registration_id": "reg_1", "event_id": event_id, "form": {"name": "Asha Rao", **form}}
    if consent is not None:
        body["consent"] = consent
    return json.dumps(body)


def submit(client, key: str = API_KEY, body: str | None = None, **params):
    return client.post(
        "/v1/verifications",
        data={"payload": body or payload()},
        files={"id_image": ("id.jpg", JPEG, "image/jpeg")},
        headers=auth(key),
        params=params,
    )


def test_healthz_is_public(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_v1_requires_api_key(client):
    assert client.get("/v1/events").status_code == 401


def test_demo_events_are_seeded_for_first_tenant(client):
    events = {e["event_id"] for e in client.get("/v1/events", headers=auth()).json()}
    assert {"ai-build-challenge-blr", "campus-hack-students", "junior-coders-13-17"} <= events
    assert client.get("/v1/events", headers=auth(RIVAL_KEY)).json() == []


def test_policy_versions_increment_and_events_belong_to_one_tenant(client):
    rules = {"event_date": "2026-09-18", "min_age": 18}
    assert client.put("/v1/events/evt_1/policy", json=rules, headers=auth()).json()["version"] == 1
    assert client.put("/v1/events/evt_1/policy", json=rules, headers=auth()).json()["version"] == 2
    assert client.put("/v1/events/evt_1/policy", json=rules, headers=auth(RIVAL_KEY)).status_code == 409


def test_consent_is_required(client):
    response = submit(client, body=payload(consent=None))
    assert response.status_code == 422
    assert "Consent required" in response.text


def test_unreadable_image_asks_for_retake_and_is_idempotent(client):
    headers = auth(**{"Idempotency-Key": "reg_1-attempt-1"})
    files = {"id_image": ("id.jpg", JPEG, "image/jpeg")}
    first = client.post("/v1/verifications", data={"payload": payload()}, files=files, headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["decision"] == "action_required"
    assert body["actions"] == ["retake_id_photo"]
    assert body["consent_notice"] == "hackingly-idv-2026-09"
    again = client.post("/v1/verifications", data={"payload": payload()}, files=files, headers=headers)
    assert again.json()["verification_id"] == body["verification_id"]


def test_rejects_non_image_uploads(client):
    files = {"id_image": ("id.jpg", b"not an image", "image/jpeg")}
    response = client.post("/v1/verifications", data={"payload": payload()}, files=files, headers=auth())
    assert response.status_code == 415


def test_validation_errors_do_not_echo_personal_data(client):
    response = submit(client, body=payload(dob="31-31-2004"))
    assert response.status_code == 422
    assert "31-31-2004" not in response.text


def test_roles_are_enforced(client):
    assert submit(client, key=REVIEWER_KEY).status_code == 403  # reviewers can't submit
    vid = submit(client, key=PLATFORM_KEY).json()["verification_id"]
    review = {"action": "approve", "reviewer": "ops@hackingly"}
    assert client.post(f"/v1/verifications/{vid}/review", json=review, headers=auth(PLATFORM_KEY)).status_code == 403
    assert client.post(f"/v1/verifications/{vid}/review", json=review, headers=auth(REVIEWER_KEY)).status_code == 200
    assert client.get("/v1/usage", headers=auth(REVIEWER_KEY)).status_code == 403


def test_tenants_cannot_see_each_others_verifications(client):
    vid = submit(client).json()["verification_id"]
    assert client.get(f"/v1/verifications/{vid}", headers=auth(RIVAL_KEY)).status_code == 404
    assert client.get("/v1/verifications", headers=auth(RIVAL_KEY)).json() == []


def test_review_overrides_decision_and_is_audited(client):
    vid = submit(client).json()["verification_id"]
    review = {"action": "approve", "reviewer": "organiser@hackingly", "note": "checked in person"}
    reviewed = client.post(f"/v1/verifications/{vid}/review", json=review, headers=auth()).json()
    assert reviewed["decision"] == "verified"
    assert reviewed["automated_decision"] == "action_required"
    events = [e["event"] for e in client.get(f"/v1/verifications/{vid}/audit", headers=auth()).json()]
    assert events == ["verification.created", "verification.reviewed"]
    assert client.get("/v1/audit/integrity", headers=auth()).json()["intact"]


def test_images_are_kept_only_while_a_human_needs_them(tmp_path, signing_dir):
    from conftest import make_client

    with make_client(tmp_path, signing_dir, image_storage="all") as client:
        vid = submit(client).json()["verification_id"]
        assert client.get(f"/v1/verifications/{vid}/images/id").status_code == 401
        image = client.get(f"/v1/verifications/{vid}/images/id", headers=auth())
        assert image.content == JPEG
        assert image.headers["cache-control"] == "no-store"

    with make_client(tmp_path / "review-only", signing_dir) as client:
        vid = submit(client).json()["verification_id"]  # action_required: no human review, no image kept
        assert client.get(f"/v1/verifications/{vid}/images/id", headers=auth()).status_code == 404


def test_erasure_removes_personal_data_and_keeps_a_minimal_record(client):
    vid = submit(client).json()["verification_id"]
    erased = client.delete(f"/v1/verifications/{vid}", headers=auth(PLATFORM_KEY)).json()
    assert erased["erased_at"]
    assert all(check["details"] == {} for check in erased["checks"])
    assert client.delete(f"/v1/verifications/{vid}", headers=auth(REVIEWER_KEY)).status_code == 403


def test_async_mode_returns_a_job_to_poll(client):
    accepted = submit(client, mode="async")
    assert accepted.status_code == 202
    job_id = accepted.json()["job_id"]
    for _ in range(50):
        job = client.get(f"/v1/jobs/{job_id}", headers=auth()).json()
        if job["status"] == "done":
            break
    assert job["status"] == "done" and job["verification_id"].startswith("ver_")
    assert client.get(f"/v1/jobs/{job_id}", headers=auth(RIVAL_KEY)).status_code == 404


def test_rate_limit_returns_429_with_retry_after(tmp_path, signing_dir):
    from conftest import make_client

    with make_client(tmp_path, signing_dir, rate_limit_per_minute=2) as client:
        codes = [submit(client).status_code for _ in range(3)]
        assert codes[:2] == [200, 200]
        assert codes[2] == 429


def test_copilot_falls_back_to_rules_without_llm(client):
    vid = submit(client).json()["verification_id"]
    summary = client.get(f"/v1/verifications/{vid}/copilot", headers=auth()).json()
    assert summary["source"] == "rules"
    assert summary["suggested_action"] == "request_retake"


def test_shadow_mode_measures_agreement_before_enforcing(client):
    body = payload("national-hackathon-shadow")
    result = submit(client, body=body).json()
    assert result["enforced"] is False
    outcome = {"decision": "action_required", "source": "manual_check"}
    client.post(f"/v1/verifications/{result['verification_id']}/outcome", json=outcome, headers=auth(PLATFORM_KEY))
    comparison = client.get("/v1/stats", params={"event_id": "national-hackathon-shadow"}, headers=auth()).json()
    assert comparison["shadow_comparison"] == {
        "compared": 1,
        "agreement_rate": 1.0,
        "false_rejections": 0,
        "fraud_missed": 0,
        "sent_to_review": 0,
    }


def test_usage_reports_cost_and_review_time_saved(client):
    submit(client)
    usage = client.get("/v1/usage", headers=auth()).json()
    assert usage["verifications"] == 1
    assert usage["cost_per_verification_usd"] is not None
    assert usage["manual_review_minutes_avoided"] == 3.0


def test_jwks_publishes_the_pass_verification_key(client):
    keys = client.get("/.well-known/jwks.json").json()["keys"]
    assert keys[0]["kty"] == "EC" and keys[0]["alg"] == "ES256"
