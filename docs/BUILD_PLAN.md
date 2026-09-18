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
| Evidence | 77 tests, and `eval/run.py` over 47 SPECIMEN samples: 0 genuine rejected, 0 attacks accepted, 96% auto-verified |

## Not done

- **Never run on a real Aadhaar with the real UIDAI certificate.** This is the first thing to do at the venue.
- **Face matching and liveness are untested on real faces**, including which class index MiniFASNet calls "live" (`LIVE_CLASS` in `vision/faces.py`). If a live selfie is called a spoof, set `PEHCHAAN_LIVENESS_ENABLED=false` rather than debug during a demo.
- **Recapture (screen photo) detection is computed but disabled**; it needs a threshold calibrated on real photos of screens versus real cards (`moire_score` in the tamper check details).
- **No AISHE institution registry file**, so unknown colleges aren't flagged. Drop a CSV at `data/aishe_colleges.csv` to turn it on.
- **Aadhaar App runs against a test issuer**; production needs OVSE onboarding with UIDAI and their JWKS.
- **Single process, SQLite.** About 27 verifications/minute per process; scale with more processes, Postgres and object storage. Multi-process throughput is unmeasured.
- **No deployment.** Everything runs locally.

## At the venue, in order

1. Real documents through the real certificate path: team e-Aadhaar PDFs, physical card photos, PAN, college IDs. Fix what the parser misses; tune the blur threshold if genuine photos get asked for retakes.
2. Ask Hackingly for the anonymised sample IDs and run `eval/run.py --labels` over them.
3. One live Textract call with AWS credentials, to show the same path Hackingly already pays for.
4. A Groq key if you want the copilot summary written by an LLM instead of rules.
5. Deploy somewhere judges can reach, or run the demo from the laptop with the reset step from DEMO.md.
