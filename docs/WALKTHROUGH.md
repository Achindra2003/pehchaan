# Walkthrough

How to run it, how to use it, and what happens inside when a registration arrives.

---

# Part 1 — Using it

## 1.1 First run

```bash
cd api && uv sync                             # Python 3.11 deps
uv run python scripts/download_models.py      # YuNet, SFace, MiniFASNet, WeChat QR (~50 MB, once)
cd ../web && npm install && npm run build     # the UI the API will serve
cd ../api && uv run python scripts/demo.py    # http://localhost:8000
```

`scripts/demo.py` clears previous registrations, generates the demo cards if missing, and serves the API and UI on one port with the API key `demo-key`. Flags: `--keep` (keep history), `--port`.

Working on the code instead of demoing:

```bash
cd api && uv run uvicorn pehchaan.main:app_factory --factory --reload   # API + /docs
cd web && npm run dev                                                   # UI on :5173, proxies to :8000
```

Checks:

```bash
cd api
uv run pytest                    # 77 tests
uv run python ../eval/run.py     # regenerates eval/results.md from synthetic cards
uv run python scripts/loadtest.py --requests 61 --concurrency 12
```

## 1.2 The participant screen

| Control | What it does |
|---|---|
| **Demo cards** | One click fills the name and date, loads a synthetic SPECIMEN card and runs the verification. Dev only, and only when `demo-samples/` exists |
| **Event** | Which policy applies: age window, student-only, accepted documents, enforce or shadow |
| **Photo of your ID** | JPEG, PNG or an e-Aadhaar PDF. The PDF password is derived from the name and year of birth, so participants don't type it |
| **Selfie** | "Use the camera" captures in-page and counts as a live capture. A file from the gallery is an upload and cannot reach L4 |
| **Consent** | Required. The notice version and timestamp are stored with the decision |

Before anything uploads, the browser measures blur (variance of the Laplacian) and warns if the photo is soft. The result panel shows the decision, a confidence bar, how many checks passed, the evidence ladder, the reasons, and what to do next if something is fixable.

## 1.3 The organiser console

- **Stat strip**: registrations, auto-verified share, how many wait for a person, median time, cost per verification.
- **Review queue**: only open cases, highest priority first. Priority rises with duplicate suspicion, low confidence and minors.
- **Case view**: the ID image (kept *only* because this case needs a human), the reasons, the copilot summary, the evidence ledger (every check, its status, its findings, its milliseconds), and Approve / Reject / Ask for a retake. Closing the review deletes the image.

---

# Part 2 — Using the API from Hackingly

Every call needs `X-API-Key`. Keys carry a tenant and a role (`platform`, `reviewer`, `admin`).

## 2.1 Set the rules for an event, once

```bash
curl -X PUT localhost:8000/v1/events/ai-build-challenge-blr/policy \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{
    "title": "AI Build Challenge, Bengaluru",
    "event_date": "2026-09-18",
    "min_age": 18,
    "student_only": false,
    "mode": "shadow"
  }'
```

`mode: "shadow"` records decisions without enforcing them. Policies are versioned; every decision stores the version that produced it.

## 2.2 Verify a registration

```bash
curl -X POST localhost:8000/v1/verifications -H "X-API-Key: $KEY" \
  -H "Idempotency-Key: reg_4411-attempt-1" \
  -F 'payload={
    "registration_id": "reg_4411",
    "event_id": "ai-build-challenge-blr",
    "subject_id": "hackingly-user-77",
    "form": {"name": "Sneha Sharma", "dob": "2003-04-12", "email": "s@rvce.edu.in", "email_verified": true},
    "consent": {"accepted": true, "notice_version": "hackingly-idv-2026-09", "accepted_at": "2026-09-18T06:00:00Z"},
    "textract_response": { "Blocks": [...] }
  }' \
  -F id_image=@card.jpg -F selfie=@selfie.jpg
```

- `textract_response` is optional. **Send it and Pehchaan reads from it**, so no second OCR bill; leave it out and Pehchaan calls Textract itself or falls back to local OCR.
- `subject_id` enables the Pehchaan Pass.
- `Idempotency-Key` makes retries safe.
- Add `?mode=async` to get `202 {job_id}` immediately and poll `GET /v1/jobs/{job_id}`. A sync call that exceeds the budget answers `202` by itself, so slow days degrade instead of failing.

The reply, from a real run of the genuine demo card:

```json
{
  "verification_id": "ver_…", "decision": "verified", "automated_decision": "verified",
  "enforced": true, "confidence": 0.95, "evidence_level": 3, "evidence_source": "document",
  "reasons": [{"code": "AADHAAR_QR_VERIFIED", "effect": "info", "check": "aadhaar_qr",
               "message": "The Aadhaar QR code carries a valid UIDAI signature and matches the card."}],
  "actions": [], "flags": {"minor": false, "guardian_consent_required": false, "duplicate_suspected": false},
  "document": {"type": "aadhaar", "id_last4": "6982", "age_on_event_date": 23},
  "policy_version": "ai-build-challenge-blr@1",
  "usage": {"ocr_provider": "rapidocr", "textract_detect_pages": 0, "estimated_cost_usd": 1.7e-05},
  "pehchaan_pass": {"pass_id": "pass_…", "token": "eyJ…", "level": 3, "expires_at": "2027-09-18T…"},
  "checks": [{"check": "quality", "status": "pass", "duration_ms": 246}, "…"],
  "latency_ms": 1540
}
```

What to act on: `decision` for the outcome, `actions` for what to tell the participant, `reasons[].message` for why, and `pehchaan_pass.token` to store against the account. The token is returned **once** and never stored by Pehchaan.

## 2.3 The returning participant

```bash
curl -X POST localhost:8000/v1/verifications/pass -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{
  "registration_id": "reg_9902", "event_id": "campus-hack-students",
  "subject_id": "hackingly-user-77", "pass_token": "eyJ…",
  "form": {"name": "Sneha Sharma", "dob": "2003-04-12"},
  "consent": {"accepted": true, "notice_version": "v1", "accepted_at": "2026-09-18T06:00:00Z"}
}'
```

No document, no OCR, milliseconds. The pass still gets re-checked against *this* event's rules, so a 24-year-old's pass fails a 13–17 event. A pass is refused if it was revoked, belongs to another account, expired, or is weaker than the event requires.

## 2.4 Aadhaar App (OpenID4VP)

```bash
curl -X POST localhost:8000/v1/aadhaar-app/sessions -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"registration_id":"reg_5","event_id":"ai-build-challenge-blr","form":{"name":"Sneha Sharma"},
       "consent":{"accepted":true,"notice_version":"v1","accepted_at":"2026-09-18T06:00:00Z"}}'
# -> { "qr_uri": "openid4vp://?client_id=…&request_uri=…", "requested_claims": ["ResidentName","AgeAbove18"] }
```

Show `qr_uri` as a QR code. The participant scans it with the Aadhaar App, authenticates with their face, and the app posts the credential to `/aadhaar-app/callback`. Poll `GET /v1/aadhaar-app/sessions/{id}` for the verification id. For an 18+ event this asks for a name and an age attestation only: no date of birth, no photo, no image.

## 2.5 Webhooks

Set `PEHCHAAN_WEBHOOK_URL` and `PEHCHAAN_WEBHOOK_SECRET`. Events: `verification.completed`, `verification.shadow_completed`, `verification.flagged` (a later registration implicated an earlier one), `verification.reviewed`. Verify them:

```python
import hashlib, hmac, time

def valid(body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    if abs(time.time() - int(timestamp)) > 300:          # reject replays
        return False
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)

# headers: X-Pehchaan-Timestamp, X-Pehchaan-Signature
```

## 2.6 Reviewing, measuring, erasing

```bash
curl "localhost:8000/v1/verifications?open_only=true" -H "X-API-Key: $KEY"         # the queue
curl -X POST localhost:8000/v1/verifications/$ID/review -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" -d '{"action":"approve","reviewer":"ops@hackingly","note":"met in person"}'
curl -X POST localhost:8000/v1/verifications/$ID/outcome -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" -d '{"decision":"verified"}'                 # shadow mode ground truth
curl localhost:8000/v1/stats -H "X-API-Key: $KEY"                                  # incl. shadow agreement
curl localhost:8000/v1/usage -H "X-API-Key: $KEY"                                  # cost, review minutes avoided
curl localhost:8000/v1/audit/integrity -H "X-API-Key: $KEY"                        # hash chain intact?
curl -X DELETE localhost:8000/v1/verifications/$ID -H "X-API-Key: $KEY"            # DPDP erasure
```

---

# Part 3 — How it works

## 3.1 What happens to one registration

Timings are from a real run of the genuine demo card (1.54 s total).

| Stage | Check | Does | Time |
|---|---|---|---|
| 1 | `quality` | Decodes the image (or renders the e-Aadhaar PDF, deriving its password), measures blur and glare, checks size, finds faces. A failure stops here, so an unusable photo never costs OCR | 246 ms |
| 2 | `extract` | In parallel: OCR (Hackingly's Textract JSON → live Textract → local RapidOCR) and QR decoding. Classifies the document from anchor text, parses fields with OCR character repair, and fills gaps from the QR only if its signature verified | 1158 ms |
| 3 | `aadhaar_qr` | Compares the UIDAI-signed data with what's printed. Agreement promotes the signed data to authoritative; a contradiction that also matches the form is the one hard rejection | 1 ms |
| 4 | `document_rules` · `tamper` · `duplicates` · `identity` · `selfie` (parallel) | Checksums and format rules; edit and recapture signals; the platform-wide duplicate graph; name and date matching; selfie match with liveness | ~190 ms |
| 5 | `eligibility` | Age on the **event** date, minors, student status, accepted documents | <1 ms |
| 6 | decide | Turns the ledger into a decision, confidence, reasons and actions | — |

Then: store, index for duplicates, write the audit entry, issue a pass if earned, fire the webhook, and re-flag any earlier registration this one implicates.

## 3.2 The evidence ladder

| Level | Reached when |
|---|---|
| L0 unusable | The quality gate failed. Retake, never a rejection |
| L1 read | Document identified and fields read |
| L2 consistent | `document_rules`, `identity` **and** `duplicates` all passed |
| L3 proven | A signature confirms the document and its data matches the card |
| L4 present | A live selfie matches the proven photo, or the Aadhaar App authenticated the face |

Levels are cumulative, and **only a check that actually passed counts**. A skipped or crashed check can't raise the level. This is why a duplicate conflict lands at L1: `duplicates` warned, so L2 was never reached. A Pehchaan Pass or an Aadhaar App credential grants its level directly, but only when `identity` also passes.

## 3.3 From evidence to a decision

Each check emits **findings**, codes from one catalog (`domain/reasons.py`). Every code carries an effect:

| Effect | Meaning | Example |
|---|---|---|
| `info` | Recorded, changes nothing | `NAME_MATCH` |
| `penalty` | Lowers confidence only | `PAN_SURNAME_INITIAL_MISMATCH` |
| `review` | A person decides | `DUPLICATE_ID_OTHER_IDENTITY` |
| `action` | The participant can fix it | `IMAGE_BLURRY` |
| `reject` | Hard evidence of ineligibility | `AGE_BELOW_MIN_CONFIRMED` |

Precedence: **reject > action > review > verified**. If the level is below the event's minimum and nothing else is blocking, the case goes to review. A crashed check becomes `CHECK_ERROR`, which is a review, never a rejection.

Only three things reject: an age outside the window from a confirmed date of birth, printed data contradicting a valid signature while matching the form, and a reviewer's decision. Everything else asks a person or asks for a retake.

Confidence starts from the level (L2 0.85, L3 0.95, L4 0.98), drops per penalty, and for a rejection reflects the strength of the evidence behind it.

## 3.4 Where things live

```
api/src/pehchaan/
  domain/        models (the contract), policy, reasons (the catalog), decision (the engine)
  pipeline/      orchestrator (stages), context (shared state), service (the three ways in), queue, checks/
  documents/     classify, parse, dates          ← deterministic field reading
  aadhaar/       secure_qr (decode + RSA verify), app_vc (OpenID4VP + SD-JWT)
  ocr/           textract (parse + client), rapid (local fallback)
  vision/        faces (YuNet, SFace, MiniFASNet), qr (WeChat detector)
  store/sqlite   verifications, blobs, duplicate index, passes, audit chain
  security       crypto, API keys, roles, rate limiting     passes  jose  copilot  webhooks
web/src/         Verify (participant), Console (organiser), api/ (typed client), lib/quality (on-device blur)
eval/run.py      synthetic cards or --labels for real ones -> results.md
```

To add a check: write a class with `run(ctx) -> CheckResult` in `pipeline/checks/`, add its codes to the catalog, register it in `build_checks`, and add it to a stage in `STAGES`. Nothing else changes: decisions, reasons, audit and the console pick it up.

## 3.5 What is kept, and what isn't

| Data | Kept? |
|---|---|
| ID and selfie images | Only while a human review is open (`image_storage=review_only`), encrypted, deleted when the review closes |
| Aadhaar number | Never in full: last 4 digits plus a keyed HMAC for duplicate detection |
| Secure QR contents | Never stored; read in memory, verified, discarded |
| Names, faces | Encrypted at rest, tenant-scoped |
| Decisions, reasons, timings | Kept, with a hash-chained audit entry per event |

## 3.6 When things go wrong

| Situation | Behaviour |
|---|---|
| A check crashes | `CHECK_ERROR` → review. Never a rejection |
| Textract is down | Falls back to local OCR; the participant notices nothing |
| The UIDAI certificate is missing | QR signatures aren't checked; L3 is unreachable and the decision says so |
| Face models missing | Selfie check reports an error and the case goes to review rather than passing silently |
| Too many requests | Bounded queue; `429` with `Retry-After` once full |
| A slow verification | `202` plus a job id, and the webhook when it finishes |
| Fraud found later | The earlier registration is pulled back into review and any pass issued from it is revoked |
