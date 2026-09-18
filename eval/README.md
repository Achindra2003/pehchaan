# Evaluation

```bash
cd api
uv run python ../eval/run.py                                        # synthetic SPECIMEN cards
uv run python ../eval/run.py --labels ../eval/data/private/labels.csv --certs certs   # real samples
```

Both write `eval/results.md`. The real-sample run reads the images next to `labels.csv` and needs the real
UIDAI certificate directory, so the signed-QR path is exercised for what it actually is.

One command should print the numbers we show the judges:

| Metric | Why it matters |
|---|---|
| False rejection rate on genuine IDs | The problem statement's first constraint: never block legitimate participants |
| Genuine → review rate | Friction and organiser workload |
| Auto-verify rate | How much manual work disappears |
| Catch rate per attack | Does it actually stop fraud |
| p50 / p95 latency, cost per verification | Feasibility at Hackingly's scale |

## Data

- `data/synthetic/`: generated cards with a visible **SPECIMEN** watermark. Safe to commit.
- `data/private/`: team members' own IDs (with consent) and Hackingly's anonymised samples. **Git-ignored. Never commit, never upload anywhere else.**
- `labels.csv` (copy `labels.example.csv`): one row per sample.

| Column | Meaning |
|---|---|
| `event_policy` | Named policy from the eval runner (`adult_open`, `student_only`, `school_13_17`) |
| `expected_decision` | `verified`, `needs_review`, `action_required`, `not_eligible` |
| `attack` | `none`, `edited_dob`, `photo_swap`, `reused_id_new_name`, `screen_replay`, `synthetic_card`, `underage`, `expired_college_id`, `blurry`, `selfie_mismatch` |

A genuine sample scores as a **false rejection** only if it ends `not_eligible`. `needs_review` on a genuine sample counts as friction, not an error.
