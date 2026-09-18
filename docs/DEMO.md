# Demo runbook

Four cases, about three minutes, one screen. Everything else (passes, Aadhaar App, shadow mode, tenancy, usage) is an answer to a question, not part of the run.

## Before the judges arrive

```bash
# 1. Fresh demo database, so duplicates start clean
cd api && rm -rf demo-data

# 2. Real UIDAI certificate if you have it, otherwise the TEST one for the specimen cards
uv run python scripts/make_demo_samples.py      # writes demo-samples/ (git-ignored)

# 3. API
PEHCHAAN_API_KEYS="change-me-admin:hackingly:admin" \
PEHCHAAN_UIDAI_CERT_PATH="demo-samples/certs" \
PEHCHAAN_OCR_PROVIDER=rapidocr \
PEHCHAAN_DATA_DIR=demo-data \
uv run uvicorn pehchaan.main:app_factory --factory --port 8000

# 4. Web
cd ../web && npm run dev        # http://localhost:5173
```

Check `GET /v1/status` shows the certificate loaded. Have `demo-samples/README.md` open: it lists the name and date of birth to type for each card. **Use real IDs if the team is willing** — the specimen cards are the fallback.

Reset between rehearsals: stop the API, `rm -rf demo-data`, start again.

## The run

| # | Case | What to do | What they see |
|---|---|---|---|
| 0 | The hook (20 s) | "Generative models make perfect fake Aadhaar cards, and vision models score at chance on AI-edited documents. So we don't judge pixels: we check what's signed, what agrees, and what we've seen before." | — |
| 1 | Genuine (40 s) | Real Aadhaar or `genuine.jpg` | **Verified, L3, ~95%, about 2 s**, reasons listed, Pehchaan Pass issued |
| 2 | Edited DOB (40 s) | `edited-dob.jpg`, type the DOB as printed | **Not eligible**: "The date of birth printed on the card differs from the UIDAI-signed QR code" |
| 3 | Same ID, new name (40 s) | `reused-id.jpg` with a different name | **Needs review**, and the earlier genuine registration is pulled back into review too |
| 4 | Blurry (20 s) | `blurry.jpg` | **Action required**: retake, nobody rejected. The blur check also runs on the phone before upload |
| 5 | Organiser (40 s) | Switch to Organiser | Queue ordered by priority, evidence ledger per check, copilot summary, approve/reject, and the ID image kept **only** because a human needs it |

Close with the numbers: **0 genuine rejected, 0 attacks accepted, 96% auto-verified across 47 samples** (`eval/results.md`), one API call after their Textract step, shadow mode before enforcing.

## Questions to expect

- **"What about a fake PAN or college ID with no QR?"** Nothing to verify against, so it leans on format rules, form consistency, the duplicate graph and human review. We don't claim pixel forensics works; the benchmarks say it doesn't.
- **"How fast, how much?"** About 2 s per verification, ~27 per minute per process, scale by adding processes. Cost is the Textract page they already pay for, plus paise of compute. `GET /v1/usage`.
- **"Is this legal with Aadhaar?"** Offline verification only, QR data never stored, masked number, consent recorded, deletion on request. Production needs OVSE registration.
- **"Where does it go next?"** The Aadhaar App (OpenID4VP): name and `AgeAbove18` only, face-authenticated in the app, no image at all. The verifier is built and tested against a test issuer.
- **"What if the model is wrong?"** No model decides. Checks produce evidence, versioned rules decide, every decision has reason codes and a hash-chained audit entry.
