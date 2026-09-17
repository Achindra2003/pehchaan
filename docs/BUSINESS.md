# Business case

## The problem in Hackingly's words

Hackingly (50k+ developers, 500+ hackathons and bootcamps, school competitions, a jobs and internships marketplace) runs registration for age-restricted, student-only and ID-gated events. Its Textract pipeline reads a date of birth; it cannot tell a fake from a real card, catch one ID used under several names, or confirm who is registering. Manual checking doesn't scale, and blocking genuine students costs participants and support time.

The market is moving the same way: HackerOne made ID verification mandatory for bug-bounty payouts (renewed every 12 months), and government hackathons disqualify duplicate accounts. Prize pools, sponsor perks and hiring pipelines all depend on "one real, eligible person per registration".

## What Pehchaan changes

| Before | With Pehchaan |
|---|---|
| Textract reads a DOB; organisers eyeball IDs | Decision, confidence and reason for every registration in about 2 s |
| Fakes and edits pass if the DOB looks right | Signed Aadhaar QR / Aadhaar App credentials prove the data; edits contradicting the signature are rejected |
| The same ID under five names goes unnoticed | Platform-wide duplicate graph (ID hash, image, face, device) flags both registrations |
| Every returning participant is checked again | Pehchaan Pass: verified once, reused at every later event in milliseconds |
| Unclear cases block students or slip through | Uncertain cases become a one-tap retake or a prioritised human review |
| No evidence trail | Hash-chained audit log, reason codes, policy versions |

## Unit economics (per verification)

| Cost line | Estimate | Basis |
|---|---|---|
| OCR when Hackingly sends its Textract JSON | $0 | Reuses the call Hackingly already pays for |
| OCR otherwise | $0.0015 DetectDocumentText, +$0.015 only if Queries are needed | AWS list prices (US West; Mumbai to confirm) |
| Local OCR fallback | $0 external | RapidOCR on CPU |
| Compute | ~2.3 s CPU per document verification | `scripts/loadtest.py`, 16-thread laptop, one process |
| Pass reuse | ~0 | No OCR, no image, a signature check |
| Copilot summary | Only on review cases | Rules-based fallback costs nothing |
| Human review | 3 min assumed per manual check | Configurable; `GET /v1/usage` reports minutes avoided |

On the synthetic eval set, 96% of genuine participants were auto-verified and 0% were rejected, so manual review applies to a small minority instead of everyone. Every number is re-measurable with `eval/run.py` and `/v1/usage` on real samples.

## How Hackingly can make money from it

1. **Verified events (organiser plan).** Organisers of age-restricted, student-only or prize-heavy events pay per verified participant; community events stay on a free tier. Price well above a cost measured in paise per verification.
2. **Sponsor and hiring value.** "Verified unique participants" is a metric sponsors pay for and a filter hiring partners want in the jobs and internships marketplace.
3. **Pehchaan Pass as a platform moat.** Returning participants skip verification at every Hackingly event: less friction than any competitor platform, lower cost per event, and a reason for organisers to stay.
4. **API for other programmes.** Colleges, scholarship programmes and corporate challenges have the same eligibility problem; the tenancy model already supports separate customers.

## Adoption path (low risk for Hackingly)

1. **Shadow mode** on live events: Pehchaan decides but doesn't enforce; Hackingly records its own outcomes (`POST /v1/verifications/{id}/outcome`) and `GET /v1/stats` reports agreement, false rejections and missed fraud.
2. **Enforce on one event type** (for example 18+ open events) once false rejections are zero.
3. **Turn on passes** so returning participants stop paying the verification cost.
4. **Aadhaar App verification** after OVSE onboarding: the strongest evidence with the least data.

## Why build rather than buy a KYC vendor

IDfy, HyperVerge and Signzy are BFSI-grade KYC suites with quote-based pricing (Setu reported around ₹5 per verification). They don't know event rules (age on the event date, student-only, accepted documents), can't use Hackingly's cross-event participant graph, and send participants' identity data to a third party. Pehchaan keeps the data and the moat with Hackingly.

## Compliance as a selling point

DPDP obligations (consent, security, retention, verifiable parental consent for under-18s) become enforceable on **13 May 2027**. Pehchaan already records consent, minimises and deletes data, flags minors for guardian consent and supports erasure requests, so Hackingly is ready early rather than late.
