# Pehchaan · पहचान

**Identity and eligibility verification for Hackingly registrations.** From one photo of an ID, Pehchaan returns a decision, a confidence score and a plain-language reason. It plugs in after Hackingly's existing Textract step and never blocks a genuine student on an uncertain signal.

Built for **PS-003 · Hackingly platform track**, AI Build Challenge, Bengaluru, 18 Sep 2026.

## Results on 47 synthetic SPECIMEN samples ([eval/results.md](eval/results.md))

| Genuine participants rejected | Attacks accepted | Genuine auto-verified | Expected decisions |
|---|---|---|---|
| **0%** (0/23) | **0%** (0/24) | 96% | 47/47 |

Attacks covered: edited DOB, edited DOB with the QR hidden, same ID under a new name, forged QR signature, QR transplanted from another card, under-age, over-age, expired college ID, missing student proof, blurry photo, invalid ID number.

## Why it's different

Generative models can now produce convincing Aadhaar and PAN cards, and vision-model forgery judges score at chance on AI-edited documents ([research](docs/RESEARCH.md)). So Pehchaan **trusts what can't be faked**:

1. **Signed**: the UIDAI signature in the Aadhaar Secure QR, or a UIDAI-signed Aadhaar App credential
2. **Consistent**: form, OCR, QR, face, college email and institution must agree
3. **Seen before**: the same ID, image, face or device under another identity, across every Hackingly event
4. **Pixels**: edit and recapture signals, which can only ask for review or a retake, never reject

A deterministic, versioned policy engine turns the evidence into `verified`, `action_required`, `needs_review` or `not_eligible`. AI reads, matches and explains. Rules decide.

## Three ways to verify

| Evidence | Endpoint | Data kept |
|---|---|---|
| Photo or e-Aadhaar PDF | `POST /v1/verifications` | Image only while a human reviews it |
| Pehchaan Pass (returning participant) | `POST /v1/verifications/pass` | Nothing new; milliseconds, no OCR |
| Aadhaar App (OpenID4VP, SD-JWT) | `POST /v1/aadhaar-app/sessions` | Name + `AgeAbove18`; no DOB, no image |

## Docs

| | |
|---|---|
| [Business case](docs/BUSINESS.md) | Unit economics, revenue model, adoption path, build vs buy |
| [Architecture](docs/ARCHITECTURE.md) | Evidence ladder, decisions, pipeline, API, data model |
| [Security](docs/SECURITY.md) | Threat model, data handling, DPDP and Aadhaar compliance map |
| [Research](docs/RESEARCH.md) | Standards, open-source landscape, licenses, sources |
| [Walkthrough](docs/WALKTHROUGH.md) | How to run it, use the screens, call the API, and what happens inside |
| [Demo runbook](docs/DEMO.md) | One command, the four-case run, the questions to expect |
| [Build state](docs/BUILD_PLAN.md) | What is built, what is untested |

## Run it

```bash
cd api && uv sync
uv run python scripts/download_models.py      # face, liveness and QR models
cd ../web && npm install && npm run build     # the UI is served by the API
cd ../api && uv run python scripts/preflight.py  # what's ready, what each missing piece unlocks
uv run python scripts/demo.py                 # everything on http://localhost:8000

# or run them apart, with your own settings
cp ../.env.example .env                       # PEHCHAAN_API_KEYS is key:tenant:role
uv run uvicorn pehchaan.main:app_factory --factory --reload   # http://localhost:8000/docs

uv run pytest                                 # 97 tests, including end-to-end on specimen cards
uv run python ../eval/run.py                  # regenerates eval/results.md
uv run python scripts/loadtest.py             # throughput per process
```

```bash
export KEY=change-me-platform
curl -X POST localhost:8000/v1/verifications -H "X-API-Key: $KEY" \
  -F 'payload={"registration_id":"reg_1","event_id":"ai-build-challenge-blr","subject_id":"user_42",
     "form":{"name":"Asha Rao","dob":"2004-05-11"},
     "consent":{"accepted":true,"notice_version":"v1","accepted_at":"2026-09-18T10:00:00Z"}}' \
  -F id_image=@card.jpg
```

## What's built

| Area | Built |
|---|---|
| Verification | Quality gate · Textract JSON / live Textract / local OCR · doc classification and parsing (Aadhaar, PAN, voter ID, passport MRZ, DL, college ID) · Aadhaar Secure QR signature · duplicate graph · identity match · selfie match + liveness · soft tamper signals · eligibility (age on event date, minors, student-only) |
| Business | Tenants and roles · Pehchaan Pass issue, reuse, revocation · shadow mode with agreement stats · usage and cost metering · prioritised review queue · rules or LLM copilot · signed webhooks |
| Privacy and security | Consent required · review-only image retention · erasure · encryption at rest · keyed ID hashes · hashed API keys · rate limits · hash-chained audit log · defusedxml · no PII echoed in errors |
| Scale | Bounded queue with 429 backpressure · sync→async fallback · job polling · measured at ~40 verifications/min per machine |
| Interfaces | Participant page with one-click demo cards, on-device blur check and in-page camera selfie · organiser console with queue, evidence ledger, copilot and review actions |
| Not yet | Real UIDAI certificate and JWKS · Postgres and object storage · calibration on real photos · deployment |

## Data rules

Real identity documents never enter git. Synthetic cards carry a `SPECIMEN` watermark and are signed with a local TEST key, never a UIDAI key. Run `pre-commit install` once for secret scanning.
