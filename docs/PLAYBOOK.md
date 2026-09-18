# Playbook for 18 September

Five parameters, 20 marks each, one 30-minute round at 13:30. This is what a 20/20 answer looks like for each,
and how to spend the three build hours so you can give it.

No plan guarantees 100. What a plan can do is remove every avoidable way to lose marks: a demo that doesn't run,
an answer nobody on the team can give, a claim a judge catches. That's what this is for.

---

## 1. The clock

| Time | Block | What matters |
|---|---|---|
| 10:00–10:30 | Arrive | Setup and preflight. Nothing else |
| 11:00 | Build begins | Real IDs first. Not features |
| 11:00–12:30 | Build | Real documents, fix what they break |
| 12:30–13:00 | Build | Freeze. Only fixes that a judge would see |
| 13:00–13:20 | Rehearse | Two full run-throughs, out loud, with the laptop |
| 13:20–13:30 | Reset | Fresh data, screens open, phone charged |
| 13:30–14:00 | **Evaluation** | 3–5 minutes per judge wave, 100% of your score |
| 14:30 | Closing | |

---

## 2. Setup (10:00–10:30)

```bash
cd D:\Downloads\Hackathon\pehchaan\web && npm run build
cd ..\api && uv run python scripts/preflight.py
```

Preflight must show **ready** for python packages, face models, QR models, demo cards and web build. The one line
that will say `missing` is the UIDAI certificate until you add it:

```bash
# put the real UIDAI certificate (.cer) in api\certs\ then:
cd api && set PEHCHAAN_UIDAI_CERT_PATH=certs && uv run python scripts/demo.py
```

Open http://localhost:8000, click the **Genuine** card once. If it says Verified, you are ready to build.

**Hard rule for the day: if the demo works, stop touching the demo path.** Every change after 13:00 is a risk
against 20 marks of Execution.

---

## 3. Build window (11:00–13:30), in priority order

### Priority 1 — Real documents (11:00–12:00). Do this first, always.

Nothing in this project has touched a real Aadhaar. This hour converts "we built a system" into "it worked on my
card", which is the difference between a good score and a top one on Execution.

1. Every team member: photograph your own Aadhaar (or e-Aadhaar PDF), and submit it through the participant screen.
2. Expected: **Verified, L3**. Write down what actually happens for each person.
3. Then try a PAN and a college ID. Expected **Verified, L2**.
4. Then your name typed three ways: exact, initials ("A. Rao"), and misspelled. Expected: verified, review, review.
   Nothing should be rejected.

| What goes wrong | Fix, in order |
|---|---|
| A genuine photo asks for a retake | Check `quality.blur_score` in the response. If good photos score under 40, lower `BLUR_THRESHOLD` in `pipeline/checks/quality.py` |
| The QR never reads from a phone photo | Use the **e-Aadhaar PDF** path for the demo and say so. Don't fight the camera at the venue |
| L2 instead of L3 on a real card | The certificate isn't loading. `GET /v1/status` should list your `.cer`, not `test-uidai-NOT-REAL.pem` |
| A real name fails to match | Capture the exact pair and add it to `test_documents.py`; the matcher is in `names.py` |
| Selfie called a spoof | `PEHCHAAN_LIVENESS_LIVE_INDEX=1`. If still wrong, `PEHCHAAN_LIVENESS_ENABLED=false` and move on |

### Priority 2 — Ask Hackingly for the anonymised samples (11:00, in parallel)

Their problem statement offers them. If you get them:

```bash
cd api && uv run python ../eval/run.py --labels ..\eval\data\private\labels.csv --certs certs
```

"We ran it on your own samples this morning" is the strongest sentence available to you, and it takes one command.

### Priority 3 — The two five-minute wins (12:00–12:30)

- **Groq key** → `PEHCHAAN_LLM_PROVIDER=groq`, `PEHCHAAN_GROQ_API_KEY=…`. The console then shows a real LLM
  summary, which is visible evidence for the 20 marks of "Use of AI".
- **AWS keys** → `PEHCHAAN_TEXTRACT_ENABLED=true`. Then one verification runs through the real Textract path, and
  "we built on your existing pipeline" becomes something you showed, not something you said.

### Priority 4 — Only if all of the above is done (12:30–13:00)

Calibrate screen detection with 10 real photos (`scripts/calibrate_recapture.py`), or add an AISHE college CSV.
Neither is worth risking the demo for.

### 13:00 — Freeze

Run `uv run pytest` once. If green, commit and stop. If red, revert to the last green commit. No exceptions.

---

## 4. The run (3–5 minutes)

Roles, because all 4–5 members are expected to take part:

| Role | Does |
|---|---|
| Driver | Laptop only. Clicks cards. Says nothing |
| Narrator | Hook, four beats, closing numbers |
| Fraud | Takes over on the Organiser screen |
| Privacy & scale | Answers data and load questions |
| Integration | Answers "how do we plug this in" and cost |

### Word for word

**Hook (20 s).** "Hackingly's Textract pipeline reads a date of birth off an ID. It can't tell a real card from a
fake one. And generative models now make perfect fake Aadhaars: on the 2026 benchmarks, an AI judge scores 0.51
AUC on AI-edited documents, a coin flip. So we don't judge pixels. Every Aadhaar carries a QR code signed by UIDAI
with a 2048-bit key. We verify that signature offline and compare it with what's printed."

**Beat 1 — Genuine (40 s).** Click **Genuine**, or better, use a real card. "Two seconds. Verified. Level 3:
signature verified, name matches the form, age checked on the event date, not today. And every reason is shown to
the participant."

**Beat 2 — Edited DOB (40 s).** Click **Edited Dob**. "This is a minor who edited the year to look 22. The card
says 2003. The signature says 2010. Not eligible, with the exact reason. No model was asked to guess."

**Beat 3 — Reused ID (40 s).** Click **Reused Id**. "Same card, different name. Both registrations go to review,
including the one we approved thirty seconds ago, because the impostor may have registered first. That's the
cross-event graph, and it only works if you're the platform — a KYC vendor can't see it."

**Beat 4 — Blurry (20 s).** Click **Blurry**. "A quarter of a second, and it asks for a retake. Their brief says
minimise false positives: a bad photo is never a rejection. That's why zero genuine participants were rejected in
our tests."

**Beat 5 — Organiser (40 s).** Switch tabs. "The queue is ordered by risk. Every check, its result, its
milliseconds. The copilot summarises the case, cites the checks, and cannot decide anything. The ID image is here
only because this case needs a human — when the review closes, it's deleted."

**Close (30 s).** "Across 47 test cases: zero genuine participants rejected, zero attacks accepted, 96%
auto-verified. One API call after the Textract they already run. About a tenth of a paisa each. And they can run
it in shadow mode first, so nobody gets blocked while they check that it works."

### The 90-second version

Genuine → Edited DOB → the closing numbers. Nothing else.

---

## 5. What earns 20/20, parameter by parameter

### Problem Understanding & Relevance

Their brief names one constraint above the others: **minimise false positives**. Say it back to them and show it.

- Say: "Their brief says the system must not block legitimate participants. Zero genuine rejections in our tests,
  and uncertain cases become a retake or a human review — never a rejection."
- Show: the blurry card, and the "needs review" path.
- **Loses marks:** describing your architecture before naming their problem.

### Solution Quality & Problem-Solution Fit

- Say: the trust hierarchy in one breath — "signed, consistent, seen before, and pixels last, because the
  benchmarks say pixel forensics is a coin flip against AI-edited documents."
- Show: the evidence ladder L0–L4 on screen, and the reason list.
- **Loses marks:** claiming to detect fakes by looking at them. Judges may know the research.

### Execution & Working Prototype

- Show: four live cases in two minutes, from one screen, with real timings. A real Aadhaar if you have one.
- Have ready: `uv run pytest` (97 tests) and `eval/results.md`.
- **Loses marks:** a demo that needs a file picker, an internet connection, or an apology.

### Innovation & Use of AI

This is where a careful design can be under-read. **Name the AI out loud:**

- Say: "AI reads and matches: Textract and PaddleOCR models for the document, YuNet and SFace for faces,
  MiniFASNet for liveness, a statistical name matcher for Indian names, and an LLM that writes the reviewer's
  summary. Rules decide. We use AI where it works, and the benchmarks say it doesn't work for judging forgeries."
- Show: the copilot summary in the console (with the Groq key, it says `llm`).
- Also: the blur check runs on the participant's device, and every model is a small ONNX file — worth saying with
  Qualcomm in the room.
- **Loses marks:** saying "we don't really use AI, we use rules." Same design, wrong framing.

### Feasibility, Impact & Potential

- Say: "One API call after their Textract step. Shadow mode first, so they measure before enforcing. About a
  tenth of a paisa per check, against roughly ₹5 from a KYC vendor. Forty verifications a minute per machine,
  measured. And a participant verified once is re-verified free at every later event, so it gets cheaper as
  Hackingly grows."
- Show: `/v1/usage` if asked.
- **Loses marks:** a vague "it scales". Give the measured number and the limit.

---

## 6. Questions, with answers

| Question | Answer |
|---|---|
| "Did you test this on a real Aadhaar?" | Say exactly what's true that morning. If yes: "Yes — mine, this morning, verified at level 3." If no: "Not yet. Synthetic cards signed with our own test key; the signature path is identical, and we'd validate on your anonymised samples on day one." |
| "What about a fake PAN or a college ID with no QR?" | "Nothing cryptographic to check, so it falls back to format rules, consistency with the form, the duplicate graph and human review. We don't claim pixel forensics works — the benchmarks say it doesn't." |
| "Why not use more AI?" | The AI list, then: "A model that can't explain itself can't give a participant a reason they can appeal, and can't be replayed months later for a dispute." |
| "How fast? How much?" | "1.2 seconds unloaded, about 40 a minute per machine, measured. Cost is the Textract page they already pay for, plus about a tenth of a paisa." |
| "How does it scale?" | "One verification already uses several cores, so we cap in-flight work and queue the rest; bursts return a job id and a webhook. Capacity comes from more machines. Four worker processes measured the same as one, so it's CPU-bound, not GIL-bound." |
| "Is this legal with Aadhaar?" | "Offline verification only. The QR contents are never stored, the number is never stored in full, consent is recorded, and there's a deletion endpoint. Production needs Hackingly registered as an Offline Verification Seeking Entity." |
| "What about DPDP?" | "Consent, minors flagged for guardian consent, data minimised and deleted, erasure supported. The obligations become enforceable on 13 May 2027, so they'd be early." |
| "Whose code is this?" | "MIT, Apache-2.0 and BSD only. We deliberately avoided TruFor, DocTamper and InsightFace's models because their licences don't allow this use. Licence table is in the repo." |
| "What happens if a check crashes?" | "It becomes a review, never a rejection. A check that can't run also can't raise the evidence level." |
| "Could someone use their friend's card?" | "Name and date must match the form, the face on the ID is compared with a live selfie when there is one, and the same card under a second name flags both registrations." |
| "What's next?" | "The Aadhaar App: OpenID4VP with a signed credential, name and an 18+ attestation only, face-authenticated in the app. No image at all. The verifier is built and tested against a test issuer." |
| "What did each of you build?" | Have an answer each. All members are expected to take part. |

---

## 7. When something breaks

| Problem | Do this |
|---|---|
| The app won't start | `uv run python scripts/preflight.py`. It names the missing piece and the command |
| A real card fails live | Switch to the demo cards without comment, finish the run, explain afterwards |
| The QR won't read | Use the e-Aadhaar PDF, or say "this is the retake path" and show it as a feature |
| The copilot hangs | It falls back to the rules summary after 8 seconds. Keep talking |
| Duplicate flags fire unexpectedly | You reused a card. Say "that's the duplicate check" and move on; restart between waves |
| No internet | Everything except the LLM copilot and live Textract works offline |
| The laptop dies | A second laptop with the repo, `uv sync` done, and models downloaded is worth the ten minutes |

---

## 8. What not to do

- Don't demo passes, the Aadhaar App, tenancy, shadow mode or usage unless asked. They're depth for questions,
  noise in a three-minute run.
- Don't claim anything you haven't run. One caught overclaim costs more than a missing feature.
- Don't rebuild the UI at 13:15.
- Don't let one person do all the talking when the rules say all members participate.
