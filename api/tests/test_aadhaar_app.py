"""Aadhaar App verification over OpenID4VP with SD-JWT, against a TEST issuer standing in for UIDAI."""

from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlparse

from conftest import API_KEY
from cryptography.hazmat.primitives.asymmetric import ec
from helpers import CONSENT

from pehchaan import jose
from pehchaan import specimens as sp

HEADERS = {"X-API-Key": API_KEY}


def start(client, event: str, name: str = "Asha Rao") -> dict:
    registration = {
        "registration_id": f"app-{event}-{name}",
        "event_id": event,
        "form": {"name": name},
        "consent": CONSENT,
    }
    response = client.post("/v1/aadhaar-app/sessions", json=registration, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def fetch_request(client, session: dict) -> dict:
    request_uri = parse_qs(urlparse(session["qr_uri"]).query)["request_uri"][0]
    response = client.get(urlparse(request_uri).path)
    assert response.status_code == 200, response.text
    _, request, _, _ = jose.split(response.text)
    return request


def wallet_response(client, session: dict, signing_dir, claims: dict, disclose: set[str], issuer=None) -> dict:
    """Play the Aadhaar App: fetch the request, share chosen claims, post the presentation."""
    request = fetch_request(client, session)
    issuer = issuer or sp.make_test_uidai_issuer(signing_dir)
    holder = ec.generate_private_key(ec.SECP256R1())
    issued = sp.issue_test_aadhaar_credential(issuer, holder, claims)
    token = sp.present_test_credential(issued, disclose, holder, audience=request["client_id"], nonce=request["nonce"])
    posted = client.post("/aadhaar-app/callback", json={"txn": request["state"], "token": token})
    assert posted.status_code == 200, posted.text
    status = client.get(f"/v1/aadhaar-app/sessions/{session['session_id']}", headers=HEADERS).json()
    result = client.get(f"/v1/verifications/{status['verification_id']}", headers=HEADERS).json()
    return {"status": status["status"], **result}


def test_request_asks_only_for_what_an_18_plus_event_needs(client):
    session = start(client, "ai-build-challenge-blr")
    assert session["requested_claims"] == ["ResidentName", "AgeAbove18"]


def test_age_attestation_verifies_without_ever_seeing_a_date_of_birth(client, signing_dir):
    session = start(client, "ai-build-challenge-blr")
    claims = {"ResidentName": "Asha Rao", "Dob": "11-05-2004", "AgeAbove18": True, "MaskedUID": "XXXXXXXX4821"}
    result = wallet_response(client, session, signing_dir, claims, disclose={"ResidentName", "AgeAbove18"})
    assert result["decision"] == "verified"
    assert result["evidence_source"] == "aadhaar_app"
    assert result["evidence_level"] == 4
    assert result["document"]["age_on_event_date"] is None


def test_minor_is_rejected_on_signed_date_of_birth(client, signing_dir):
    session = start(client, "junior-coders-13-17", "Kavya Iyer")
    assert session["requested_claims"] == ["ResidentName", "Dob"]
    claims = {"ResidentName": "Kavya Iyer", "Dob": "01-01-2005"}
    result = wallet_response(client, session, signing_dir, claims, disclose={"ResidentName", "Dob"})
    assert result["decision"] == "not_eligible"


def test_credential_from_an_untrusted_issuer_is_refused(client, signing_dir):
    session = start(client, "ai-build-challenge-blr", "Rahul Nair")
    rogue = ec.generate_private_key(ec.SECP256R1())
    claims = {"ResidentName": "Rahul Nair", "AgeAbove18": True}
    result = wallet_response(client, session, signing_dir, claims, {"ResidentName", "AgeAbove18"}, issuer=rogue)
    assert result["status"] == "failed"
    assert result["decision"] == "action_required"


def test_completed_session_cannot_be_replayed(client, signing_dir):
    session = start(client, "ai-build-challenge-blr", "Meera Rao")
    claims = {"ResidentName": "Meera Rao", "AgeAbove18": True}
    wallet_response(client, session, signing_dir, claims, {"ResidentName", "AgeAbove18"})
    request_uri = parse_qs(urlparse(session["qr_uri"]).query)["request_uri"][0]
    assert client.get(urlparse(request_uri).path).status_code == 404


def test_claim_dates_are_parsed_in_uidai_format():
    from pehchaan.aadhaar.app_vc import _parse_date

    assert _parse_date("11-05-2004") == date(2004, 5, 11)
