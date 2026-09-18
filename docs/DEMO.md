# Demo runbook

Four cases, about three minutes, one screen. Everything else (passes, Aadhaar App, shadow mode, tenancy, usage) is an answer to a question, not part of the run.

## The day (from the organisers' rules)

| | |
|---|---|
| Arrive | 10:00–10:30 · Startup Park, Koramangala |
| Build | 11:00–13:30 (three hours) |
| **Final Evaluation** | **13:30–14:00** · the only scored round, 100% of marks |
| Closing | 14:30 onwards |
| Team | 4–5 members, all expected to take part |

Thirty minutes covers every team, so assume **3–5 minutes each** with judges coming to the table, probably in waves. The demo must cover, in their words: **problem, solution, AI integration, implementation, and intended user value.**

### Scoring: five parameters, 20 marks each

| Parameter | What we show, in one line |
|---|---|
| Problem Understanding & Relevance | "Their brief says minimise false positives. Zero genuine participants were rejected; uncertain cases get a retake or a human." |
| Solution Quality & Problem-Solution Fit | The trust hierarchy: signed, consistent, seen before, pixels last — and why pixel forensics can't be the backbone |
| Execution & Working Prototype | Four live cases, real decisions in ~2 s, 97 tests, `eval/results.md` |
| Innovation & Use of AI | Name the AI parts out loud (OCR, face match, liveness, name matching, LLM copilot), then the split: **AI gathers evidence, rules decide** |
| Feasibility, Impact & Potential | One API call after their Textract step, shadow mode before enforcing, ~₹0.001 per check, 40/min per machine, passes make repeat checks free |

**Say the AI list out loud.** "Use of AI" is 20 marks and our design deliberately keeps models out of the decision, so a judge who doesn't hear the list may score it as light. The strongest framing: *we use AI where it works, and the benchmarks say it doesn't work for judging forgeries, so rules decide and every decision is explainable.*

### If asked about third-party code (it's in their rules)

`docs/RESEARCH.md` has the licence table: MIT, Apache-2.0 and BSD components only, and we deliberately avoided TruFor (non-profit use only), DocTamper (non-commercial dataset) and InsightFace's pretrained models (non-commercial). Synthetic cards are our own, watermarked SPECIMEN, signed with our own test key.

### Running it repeatedly for waves of judges

Use a **different card per wave**, or restart with `scripts/demo.py` between waves. Clicking the same card twice legitimately triggers the duplicate flag, which is either a great moment or a confusing one depending on whether you meant it.

## Before the judges arrive

```bash
cd web && npm run build          # once, so the UI is served from the API
cd ../api && uv run python scripts/preflight.py   # confirms models, certificate, build, keys
uv run python scripts/demo.py
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

### The 90-second version, if judges are running late

1. **Genuine** card: verified in two seconds, with the reason.
2. **Edited Dob** card: not eligible, because the signed QR contradicts the print.
3. One sentence: "0 genuine rejected and 0 attacks accepted across 47 test cases, one API call after the Textract they already run, and it costs about a tenth of a paisa."

### Who does what (4–5 people, all expected to take part)

| Role | During the demo |
|---|---|
| Driver | Laptop, clicks the cards, never narrates |
| Narrator | The hook, the four beats, the closing numbers |
| Fraud | Takes over at the Organiser screen: queue, evidence, why both registrations are flagged |
| Privacy and scale | Answers the data questions: what's stored, for how long, DPDP, ~40/min per machine |
| Integration | Answers Hackingly's question: one call after Textract, shadow mode, webhooks, cost |

## Questions to expect

- **"What about a fake PAN or college ID with no QR?"** Nothing to verify against, so it leans on format rules, form consistency, the duplicate graph and human review. We don't claim pixel forensics works; the benchmarks say it doesn't.
- **"How fast, how much?"** 1.2 s unloaded, about 40 per minute per machine, measured. Concurrency beyond that adds latency rather than throughput, so bursts go through a queue and capacity comes from more machines. Cost is the Textract page they already pay for, plus paise of compute. `GET /v1/usage`.
- **"Is this legal with Aadhaar?"** Offline verification only, QR data never stored, masked number, consent recorded, deletion on request. Production needs OVSE registration.
- **"Where does it go next?"** The Aadhaar App (OpenID4VP): name and `AgeAbove18` only, face-authenticated in the app, no image at all. The verifier is built and tested against a test issuer.
- **"What if the model is wrong?"** No model decides. Checks produce evidence, versioned rules decide, every decision has reason codes and a hash-chained audit entry.
