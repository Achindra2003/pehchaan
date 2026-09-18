# Build state and what's left

The demo script lives in [DEMO.md](DEMO.md). This is what exists and what doesn't.

## Built and tested

| Area | Detail |
|---|---|
| Reading | Quality gate (blur, glare, size, e-Aadhaar PDF with the password derived from name + year); Hackingly's Textract JSON, live Textract with Queries, or local RapidOCR; document classification and field parsing for Aadhaar, PAN, voter ID, passport MRZ, driving licence and college ID, with OCR character repair |
| Proving | Aadhaar Secure QR decode and RSA/SHA-256 signature check; signed data compared with the printed card; Aadhaar App SD-JWT verification (issuer signature, disclosures, key binding) |
| Catching | Duplicate graph (keyed ID hash, PDQ image hash, face embedding, device); identity match; selfie match with passive liveness; soft edit and recapture signals |
| Deciding | Versioned event policy, reason catalog, evidence ladder, confidence; age on the event date, year-of-birth-only cards, signed age attestations, minors, student rules |
| Running it | Tenants and roles, rate limits, bounded queue with backpressure, idempotency, signed webhooks, prioritised review queue, copilot, usage metering, hash-chained audit log, erasure, retention sweep |
| Interfaces | Participant capture page with an on-device blur check and in-page camera selfie; organiser console with queue, evidence ledger, copilot and review actions |
| Evidence | 97 tests (including the selfie decision paths and passport, voter ID and driving licence parsing), and `eval/run.py` over 47 SPECIMEN samples: 0 genuine rejected, 0 attacks accepted, 96% auto-verified |

## Not done

- **Never run on a real Aadhaar with the real UIDAI certificate.** This is the first thing to do at the venue.
- **Face matching and liveness are untested on real faces**, including which class index MiniFASNet calls "live". If a live selfie reads as a spoof, flip `PEHCHAAN_LIVENESS_LIVE_INDEX=1` or set `PEHCHAAN_LIVENESS_ENABLED=false`; no code change needed. The selfie decision paths themselves are covered by tests with a stand-in engine.
- **Recapture (screen photo) detection is computed but disabled.** A synthetic screen simulation did not separate from real photos, so calibrating on it would have been fitting to our own artifact. `scripts/calibrate_recapture.py` sets the threshold from 10 real photos in two minutes, and prints "leave it disabled" when they overlap.
- **No AISHE institution registry file**, so unknown colleges aren't flagged. Drop a CSV at `data/aishe_colleges.csv` to turn it on.
- **Aadhaar App runs against a test issuer**; production needs OVSE onboarding with UIDAI and their JWKS.
- **SQLite, one machine.** Measured at ~40 verifications/minute on a 16-thread laptop, and more worker processes did not raise it (the CPU is the limit, not the GIL). Capacity comes from more machines, with Postgres and object storage behind them.
- **No deployment.** Everything runs locally.

## At the venue, in order

1. Real documents through the real certificate path: team e-Aadhaar PDFs, physical card photos, PAN, college IDs. Fix what the parser misses; tune the blur threshold if genuine photos get asked for retakes.
2. Ask Hackingly for the anonymised sample IDs and run `eval/run.py --labels` over them.
3. One live Textract call with AWS credentials, to show the same path Hackingly already pays for.
4. A Groq key if you want the copilot summary written by an LLM instead of rules.
5. Deploy somewhere judges can reach, or run the demo from the laptop with the reset step from DEMO.md.
