# Evaluation results

47 samples (23 genuine, 24 attacks), local OCR (RapidOCR). Source: synthetic SPECIMEN cards with a TEST signing key, not a substitute for real IDs. Regenerate with `eval/run.py`.

| Metric | Result |
|---|---|
| Genuine participants rejected (BPCER) | **0% (0/23)** |
| Genuine participants auto-verified | 96% (22/23) |
| Genuine participants asked to retake or reviewed (friction) | 4% (1/23) |
| Attacks accepted as verified (APCER) | **0% (0/24)** |
| Decisions matching the expected outcome | 100% (47/47) |
| Latency p50 / p95 (CPU, local OCR) | 1792 ms / 2719 ms |
| Audit chain intact | True (56 entries) |

## Attacks

| Attack | Samples | Stopped (not verified) | Outcomes |
|---|---|---|---|
| blurry | 2 | 100% (2/2) | action_required ×2 |
| edited dob | 4 | 100% (4/4) | not_eligible ×4 |
| edited dob qr hidden | 3 | 100% (3/3) | action_required ×3 |
| expired college id | 2 | 100% (2/2) | action_required ×2 |
| forged signature | 2 | 100% (2/2) | needs_review ×2 |
| invalid id number | 2 | 100% (2/2) | needs_review ×2 |
| no student proof | 1 | 100% (1/1) | action_required ×1 |
| overage | 1 | 100% (1/1) | not_eligible ×1 |
| qr from other card | 2 | 100% (2/2) | not_eligible ×2 |
| reused id new name | 3 | 100% (3/3) | needs_review ×3 |
| underage | 2 | 100% (2/2) | not_eligible ×2 |

## Every sample

| Sample | Expected | Got | Level | Confidence | Reasons |
|---|---|---|---|---|---|
| g-aadhaar-00 | verified | verified | L3 | 0.95 | — |
| g-aadhaar-01 | verified | verified | L3 | 0.95 | — |
| g-aadhaar-02 | verified | verified | L3 | 0.95 | — |
| g-aadhaar-03 | verified | verified | L3 | 0.95 | — |
| g-aadhaar-04 | verified | verified | L3 | 0.95 | — |
| g-aadhaar-05 | verified | verified | L3 | 0.95 | — |
| g-aadhaar-06 | verified | verified | L3 | 0.95 | — |
| g-aadhaar-07 | verified | verified | L3 | 0.95 | — |
| g-aadhaar-08 | verified | verified | L3 | 0.95 | — |
| g-aadhaar-09 | verified | verified | L3 | 0.95 | — |
| g-eaadhaar-pdf | verified | verified | L3 | 0.95 | — |
| g-pan-0 | verified | verified | L2 | 0.85 | — |
| g-pan-1 | verified | verified | L2 | 0.85 | — |
| g-pan-2 | verified | verified | L2 | 0.85 | — |
| g-pan-3 | verified | verified | L2 | 0.85 | — |
| g-college-0 | verified | verified | L2 | 0.85 | — |
| g-college-1 | verified | verified | L2 | 0.85 | — |
| g-college-2 | verified | verified | L2 | 0.85 | — |
| g-college-3 | verified | verified | L2 | 0.85 | — |
| g-minor-0 | verified | verified | L3 | 0.95 | — |
| g-minor-1 | verified | verified | L3 | 0.95 | — |
| g-minor-2 | verified | verified | L3 | 0.95 | — |
| g-initials-form | needs_review | needs_review | L1 | 0.45 | LEVEL_BELOW_EVENT_MINIMUM, NAME_PARTIAL_MATCH |
| a-edited-dob-0 | not_eligible | not_eligible | L2 | 0.95 | AADHAAR_PRINT_CONTRADICTS_QR |
| a-edited-dob-1 | not_eligible | not_eligible | L2 | 0.95 | AADHAAR_PRINT_CONTRADICTS_QR |
| a-edited-dob-2 | not_eligible | not_eligible | L2 | 0.95 | AADHAAR_PRINT_CONTRADICTS_QR |
| a-edited-dob-3 | not_eligible | not_eligible | L2 | 0.95 | AADHAAR_PRINT_CONTRADICTS_QR |
| a-edited-dob-noqr-0 | action_required | action_required | L2 | 0.9 | AADHAAR_QR_REQUIRED |
| a-edited-dob-noqr-1 | action_required | action_required | L1 | 0.9 | AADHAAR_QR_REQUIRED, ID_NUMBER_INVALID |
| a-edited-dob-noqr-2 | action_required | action_required | L2 | 0.9 | AADHAAR_QR_REQUIRED |
| a-reused-id-0 | needs_review | needs_review | L1 | 0.4 | DUPLICATE_ID_OTHER_IDENTITY, LEVEL_BELOW_EVENT_MINIMUM, NAME_MISMATCH |
| a-reused-id-1 | needs_review | needs_review | L1 | 0.4 | DUPLICATE_ID_OTHER_IDENTITY, LEVEL_BELOW_EVENT_MINIMUM, NAME_MISMATCH |
| a-reused-id-2 | needs_review | needs_review | L1 | 0.4 | DUPLICATE_ID_OTHER_IDENTITY, LEVEL_BELOW_EVENT_MINIMUM, NAME_MISMATCH |
| a-forged-qr-0 | needs_review | needs_review | L2 | 0.6 | AADHAAR_QR_SIGNATURE_INVALID |
| a-forged-qr-1 | needs_review | needs_review | L1 | 0.4 | AADHAAR_QR_SIGNATURE_INVALID, ID_NUMBER_INVALID, LEVEL_BELOW_EVENT_MINIMUM |
| a-transplanted-qr-0 | not_eligible | not_eligible | L2 | 0.95 | AADHAAR_PRINT_CONTRADICTS_QR, AADHAAR_PRINT_QR_MISMATCH |
| a-transplanted-qr-1 | not_eligible | not_eligible | L2 | 0.95 | AADHAAR_PRINT_CONTRADICTS_QR, AADHAAR_PRINT_QR_MISMATCH |
| a-underage-0 | not_eligible | not_eligible | L3 | 0.9 | AGE_BELOW_MIN_CONFIRMED |
| a-underage-1 | not_eligible | not_eligible | L3 | 0.9 | AGE_BELOW_MIN_CONFIRMED |
| a-overage-junior | not_eligible | not_eligible | L3 | 0.9 | AGE_ABOVE_MAX_CONFIRMED |
| a-expired-college-0 | action_required | action_required | L2 | 0.9 | COLLEGE_ID_EXPIRED |
| a-expired-college-1 | action_required | action_required | L2 | 0.9 | COLLEGE_ID_EXPIRED |
| a-aadhaar-student-event | action_required | action_required | L3 | 0.9 | STUDENT_PROOF_REQUIRED |
| a-blurry-0 | action_required | action_required | L0 | 0.9 | IMAGE_BLURRY |
| a-blurry-1 | action_required | action_required | L0 | 0.9 | IMAGE_BLURRY |
| a-invalid-number-0 | needs_review | needs_review | L1 | 0.45 | ID_NUMBER_INVALID, LEVEL_BELOW_EVENT_MINIMUM |
| a-invalid-number-1 | needs_review | needs_review | L1 | 0.45 | ID_NUMBER_INVALID, LEVEL_BELOW_EVENT_MINIMUM |

## Not covered by this synthetic set

- Face checks (photo swap, selfie mismatch, liveness): specimen cards carry no real faces.
- Screen recapture: the moiré signal is reported but disabled until calibrated on real photos.
- AI-generated cards without a Secure QR: handled by policy (QR required for age-restricted events), not by pixels.
- Real phone photos and real UIDAI signatures: run the team's consented samples and Hackingly's anonymised set.
