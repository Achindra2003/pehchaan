# Demo runbook

Four cases, about three minutes, one screen. Everything else (passes, Aadhaar App, shadow mode, tenancy, usage) is an answer to a question, not part of the run.

## Before the judges arrive

```bash
cd web && npm run build          # once, so the UI is served from the API
cd ../api && uv run python scripts/demo.py
```

That clears earlier registrations (so duplicates fire only when you want them), makes the demo cards if they
are missing, and serves everything on **http://localhost:8000**. `--keep` keeps the history; `--port` moves it.

With real Aadhaar cards, point it at the real certificate instead of the test one:

```bash
PEHCHAAN_UIDAI_CERT_PATH=certs uv run python scripts/demo.py
```

The participant screen carries a row of **demo cards**. One click fills the form, loads the card and runs the
verification, so nothing depends on finding a file on stage. Real IDs are still the better demo; the cards are
the fallback and the rehearsal tool.

## The run

| # | Case | What to do | What they see |
|---|---|---|---|
| 0 | The hook (20 s) | "Generative models make perfect fake Aadhaar cards, and vision models score at chance on AI-edited documents. So we don't judge pixels: we check what's signed, what agrees, and what we've seen before." | — |
| 1 | Genuine (40 s) | Real Aadhaar, or the **Genuine** card | **Verified, L3, 95%, about 2 s**, 8 of 9 checks passed, Pehchaan Pass issued |
| 2 | Edited DOB (40 s) | **Edited Dob** card | **Not eligible**: "The date of birth printed on the card differs from the UIDAI-signed QR code" |
| 3 | Same ID, new name (40 s) | **Reused Id** card | **Needs review**, and the earlier genuine registration is pulled back into review too |
| 4 | Blurry (20 s) | **Blurry** card | **Action required** in 0.25 s: retake, nobody rejected. The same blur check runs on the phone before anything uploads |
| 5 | Organiser (40 s) | Switch to Organiser | Queue ordered by priority, evidence ledger per check, copilot summary, approve/reject, and the ID image kept **only** because a human needs it |

Close with the numbers: **0 genuine rejected, 0 attacks accepted, 96% auto-verified across 47 samples** (`eval/results.md`), one API call after their Textract step, shadow mode before enforcing.

## Questions to expect

- **"What about a fake PAN or college ID with no QR?"** Nothing to verify against, so it leans on format rules, form consistency, the duplicate graph and human review. We don't claim pixel forensics works; the benchmarks say it doesn't.
- **"How fast, how much?"** About 2 s per verification, ~27 per minute per process, scale by adding processes. Cost is the Textract page they already pay for, plus paise of compute. `GET /v1/usage`.
- **"Is this legal with Aadhaar?"** Offline verification only, QR data never stored, masked number, consent recorded, deletion on request. Production needs OVSE registration.
- **"Where does it go next?"** The Aadhaar App (OpenID4VP): name and `AgeAbove18` only, face-authenticated in the app, no image at all. The verifier is built and tested against a test issuer.
- **"What if the model is wrong?"** No model decides. Checks produce evidence, versioned rules decide, every decision has reason codes and a hash-chained audit entry.
