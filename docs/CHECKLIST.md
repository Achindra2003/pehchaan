# Venue checklist

Print this or keep it open. Detail is in [PLAYBOOK.md](PLAYBOOK.md).

## Bring

- [ ] Laptop + charger (and a second laptop with `uv sync` done and models downloaded)
- [ ] Phone with your own Aadhaar photo / e-Aadhaar PDF already on the laptop
- [ ] The real UIDAI certificate in `api\certs\`
- [ ] Groq key and AWS keys written down (five-minute wins)
- [ ] Mobile hotspot, in case venue wifi is bad

## 10:00–10:30 · Setup

- [ ] `cd web && npm run build`
- [ ] `cd ..\api && uv run python scripts/preflight.py` → everything **ready** except the certificate line
- [ ] Certificate in place → `GET /v1/status` lists your `.cer`, not `test-uidai-NOT-REAL.pem`
- [ ] `uv run python scripts/demo.py` → http://localhost:8000 opens
- [ ] Click **Genuine** → Verified, L3

## 11:00–12:00 · Real documents (the hour that matters)

- [ ] Each member: own Aadhaar through the participant screen → expect **Verified L3**
- [ ] One PAN → **Verified L2**
- [ ] One college ID on the student event → **Verified L2**
- [ ] Name typed as initials → **needs review** (not rejected)
- [ ] Write down anything that misbehaves, fix per the table in the playbook
- [ ] Email Hackingly for the anonymised samples; if they arrive: `eval/run.py --labels …`

## 12:00–12:30 · Five-minute wins

- [ ] `PEHCHAAN_LLM_PROVIDER=groq` + `PEHCHAAN_GROQ_API_KEY=…` → console shows Copilot (llm)
- [ ] `PEHCHAAN_TEXTRACT_ENABLED=true` + AWS keys → one run through real Textract

## 13:00 · Freeze

- [ ] `uv run pytest` green (97 tests)
- [ ] Commit
- [ ] No more changes to anything the demo touches

## 13:00–13:20 · Rehearse

- [ ] Full run out loud, with the laptop, twice
- [ ] Each person says their own line once
- [ ] Time it: under 4 minutes including questions
- [ ] 90-second version rehearsed once

## 13:20–13:30 · Reset

- [ ] Restart `scripts/demo.py` (clears duplicate history)
- [ ] Participant tab open, demo cards visible
- [ ] Second tab: Organiser. Third tab: `eval/results.md`
- [ ] Laptop plugged in, notifications off, screen brightness up
- [ ] Phone with a real card ready, if that path works

## 13:30–14:00 · Evaluation

- [ ] Hook (20 s) → Genuine → Edited DOB → Reused ID → Blurry → Organiser → numbers
- [ ] Different card per judge wave, or restart between waves
- [ ] Everyone answers something
- [ ] Say the AI list out loud — 20 marks depend on it being heard

## The four numbers to have on your tongue

- **0** genuine participants rejected
- **0** attacks accepted (47 test cases, 11 attack types)
- **96%** auto-verified, ~2 seconds each
- **₹0.001** per check, ~40 per minute per machine
