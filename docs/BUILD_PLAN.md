# Build plan

The brief asks teams to arrive with ~80% built and finish, test and ship at the venue (18 Sep 2026, 3-hour sprint).
Judged on: problem understanding · solution fit · working prototype · innovation / use of AI · feasibility and impact.

## Today, before anything else

- [ ] Email Hackingly for the **anonymised sample IDs**
- [ ] AWS account with Textract access in `ap-south-1`; keys in `.env`
- [ ] Download the **UIDAI offline verification certificate** (Indian network) into `api/certs/`
- [ ] `cd api && uv run python scripts/download_models.py` (YuNet, SFace, MiniFASNet)
- [ ] Collect consented test IDs from the team (e-Aadhaar PDF + photo of card, PAN, college ID, one selfie each) into `eval/data/private/`

## Workstreams

Every check implements the same interface (`Check.run(ctx) -> CheckResult`) and emits codes from `domain/reasons.py`, so the streams can be built in parallel without stepping on each other. Unbuilt checks live in `api/src/pehchaan/pipeline/checks/stubs.py` with their spec as the docstring; move each into its own module when you implement it.

| Stream | Scope | Where |
|---|---|---|
| **A. Core & API** | Persistence (SQLite), hash-chained audit log, signed webhooks | `pipeline/orchestrator.py`, `api/`, `store/` |
| **B. Read** | Quality gate, Textract adapter (reuse JSON, Queries fallback), doc classification | `QualityCheck`, `ExtractCheck` → `checks/quality.py`, `checks/extract.py`, `adapters/textract.py` |
| **C. Prove** | Aadhaar QR decode + signature + print/photo comparison; duplicate graph | `AadhaarQrCheck`, `DuplicatesCheck` |
| **D. Match** | Name/DOB matching, institution + email domain, selfie match + anti-spoof, edit/recapture signals | `IdentityCheck`, `SelfieCheck`, `TamperCheck` |
| **E. Experience** | Participant capture page (on-device guidance), organiser console (queue, case view, copilot), demo polish | `web/` |

Already done and tested: contract, event policy, decision engine, reason catalog, `EligibilityCheck`, `DocumentRulesCheck`, API with auth and idempotency.

## Tonight: the 80%

Must work end to end on real images:

1. **A** SQLite store replacing the in-memory one; hash-chained audit log
2. **B** Quality gate; Textract read with Queries; doc type classification
3. **C** Aadhaar Secure QR decode + signature verification + QR ↔ print comparison; HMAC duplicate check
4. **D** Name + DOB match against the form
5. **E** Capture page that uploads and shows the result; console list + case view with the evidence ledger
6. **All** Eval set labelled (`eval/labels.csv`) and `eval/run.py` printing the metrics table

## At the venue: the last 20%

1. Selfie match + MiniFASNet anti-spoofing
2. Edit/recapture signals (moiré, field-level noise, text-line geometry)
3. Face and PDQ duplicate index
4. Reviewer copilot summary
5. On-device blur/glare guidance in the capture page
6. Re-run eval, freeze numbers, rehearse the demo twice, deploy

**Cut line if time runs short**: drop the copilot and on-device guidance before anything in the "tonight" list. A smaller system that is measurably right beats a bigger one that isn't.

## Demo script (3 minutes)

1. **Hook (20 s).** An AI-generated Aadhaar that looks perfect. "Vision models are at chance on these. So we don't trust pixels; we trust signatures, consistency and the graph."
2. **Genuine student (30 s).** Phone photo of a real Aadhaar → `verified`, L3, 0.95, reasons shown, under 3 seconds.
3. **Edited DOB (30 s).** Same card with the DOB edited → signed QR contradicts the print → `not_eligible` with the exact reason.
4. **Reused ID (30 s).** Same ID under a different name → both registrations to review → console with evidence side by side and copilot summary.
5. **Blurry photo (15 s).** → `action_required`: retake guidance, nobody rejected.
6. **Minor (15 s).** → guardian consent flag.
7. **Numbers and integration (40 s).** Eval table (FRR, catch rate per attack, auto-verify rate, latency, cost); one API call after Textract; shadow mode; verified pass across events; DPDP May 2027.

## Eval set spec

`eval/labels.csv`:

```csv
sample_id,file,selfie_file,event_policy,form_name,form_dob,expected_decision,attack
g001,private/g001_aadhaar.jpg,,adult_open,Asha Rao,2004-05-11,verified,none
a001,private/a001_dob_edit.jpg,,adult_open,Asha Rao,2004-05-11,not_eligible,edited_dob
```

Attacks to cover: `none`, `edited_dob`, `photo_swap`, `reused_id_new_name`, `screen_replay`, `synthetic_card`, `underage`, `expired_college_id`, `blurry`, `selfie_mismatch`.
