# Pehchaan · पहचान

**Identity and eligibility verification for Hackingly registrations.** From one photo of an ID, Pehchaan returns a decision, a confidence score and a plain-language reason. It plugs in after Hackingly's existing Textract step and never blocks a genuine student on an uncertain signal.

Built for **PS-003 · Hackingly platform track**, AI Build Challenge, Bengaluru, 18 Sep 2026.

## Why it's different

Generative models can now produce convincing Aadhaar and PAN cards, and vision-model forgery judges score at chance on AI-edited documents ([research](docs/RESEARCH.md#2-the-finding-that-shapes-the-whole-design-pixels-can-no-longer-be-trusted)). So Pehchaan **trusts what can't be faked**:

1. **Signed**: the UIDAI signature inside the Aadhaar Secure QR, checked offline
2. **Consistent**: form, OCR, QR, face, college email and institution registry must agree
3. **Seen before**: the same ID, image or face under another identity, across every Hackingly event
4. **Pixels**: edit and recapture signals, which can only ask for review or a retake, never reject

Every check writes evidence to a ledger; a deterministic, versioned policy engine turns it into one of `verified`, `action_required`, `needs_review` or `not_eligible`. AI reads, matches and explains. Rules decide.

## Docs

| | |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | Evidence ladder, decisions, pipeline, API, data model, scale, business case |
| [Security](docs/SECURITY.md) | Threat model, data handling, DPDP and Aadhaar compliance map |
| [Research](docs/RESEARCH.md) | Sources, open-source components and licenses, competitors |
| [Build plan](docs/BUILD_PLAN.md) | Workstreams, tonight vs venue, demo script |

## Repo layout

```
api/                  FastAPI service (Python 3.11, uv)
  src/pehchaan/
    domain/           contracts, event policy, reason catalog, decision engine
    pipeline/         orchestrator + checks (one module per check)
    api/              HTTP routes, auth
    store/            persistence (in-memory for now)
  tests/
  scripts/            model downloads
web/                  participant capture page + organiser console (Vite, React, TS, Tailwind)
eval/                 labelled dataset spec and metrics runner
docs/
```

## Run it

```bash
# API
cd api
cp ../.env.example .env          # set PEHCHAAN_API_KEYS
uv sync
uv run python scripts/download_models.py
uv run uvicorn pehchaan.main:app --reload     # http://localhost:8000/docs

# Web
cd web
cp .env.example .env.local
npm install
npm run dev                                   # http://localhost:5173

# Tests
cd api && uv run pytest
```

Try it:

```bash
export PEHCHAAN_KEY=...   # one of PEHCHAAN_API_KEYS from api/.env

curl -X PUT localhost:8000/v1/events/evt_demo/policy -H "X-API-Key: $PEHCHAAN_KEY" \
  -H "Content-Type: application/json" -d '{"event_date":"2026-09-18","min_age":18}'

curl -X POST localhost:8000/v1/verifications -H "X-API-Key: $PEHCHAAN_KEY" \
  -F 'payload={"registration_id":"reg_1","event_id":"evt_demo","form":{"name":"Asha Rao","dob":"2004-05-11"}}' \
  -F id_image=@card.jpg
```

## Status

| Component | State |
|---|---|
| API contract, event policies, idempotency, auth | ✅ |
| Decision engine + reason catalog | ✅ tested |
| Eligibility (age on event date, YOB-only cards, minors, student-only) | ✅ tested |
| Document rules (Aadhaar Verhoeff, PAN, EPIC, passport) | ✅ tested |
| Quality gate · Textract extraction · Aadhaar QR proof · duplicates · identity · selfie · tamper signals | 🚧 stubs with specs in `pipeline/checks/stubs.py` |
| Persistence, audit log, webhooks | 🚧 |
| Capture page, organiser console, reviewer copilot | 🚧 |
| Eval runner | 🚧 |

## Data rules

Real identity documents never enter git. `eval/data/private/` is ignored; synthetic cards carry a `SPECIMEN` watermark. Run `pre-commit install` once to get secret scanning on every commit.
