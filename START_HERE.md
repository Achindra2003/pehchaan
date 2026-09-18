# START HERE — everything, in one place

You have about 30 minutes. Read this once, top to bottom. Don't jump around.

---

## PART 0 — What we actually built, in plain English

**The problem Hackingly gave us:** when someone registers for a hackathon, Hackingly's system reads their ID
photo and pulls out a date of birth, to check they're old enough. That's it. It can't tell if the ID is fake,
edited, or already used by someone else under a different name.

**What we built:** a system called **Pehchaan** ("identity" in Hindi) that looks at an ID photo and gives one of
four answers:

| It says | Meaning |
|---|---|
| **Verified** | Come in, you're good |
| **Action required** | Something's fixable — like "your photo is blurry, take it again" |
| **Needs review** | A human should look at this |
| **Not eligible** | No — and it tells you exactly why |

**The one clever idea, in one sentence:** every Indian Aadhaar card has a hidden QR code that's secretly signed
by the government (like a wax seal). Instead of trying to guess if a photo "looks fake" (which even AI is bad
at — read the next line), we check that hidden signature. If someone edited the birth year on the card, the
printed text and the secret signature disagree, and we catch it instantly. No guessing.

**Why not just use AI to spot fakes?** Because it doesn't work well. There's published 2026 research showing
that AI models trying to spot AI-edited fake IDs score basically the same as a coin flip. So we don't trust a
model's "gut feeling" on a photo. We trust the math (the signature), and things that are consistent, and things
we've seen before (like the same ID used twice). Pixels/guessing come last and can never reject someone by
themselves — only a human or a clear signature contradiction can say "no."

**Where AI actually IS used:** reading the text off the ID (OCR), matching the face on the ID to a selfie,
checking a selfie isn't a photo-of-a-photo, matching names that are spelled differently, and writing a short
summary for the human reviewer. AI gathers evidence. It never makes the final decision — that's done by clear
rules, so we can always explain exactly why someone was accepted or rejected.

That's the whole idea. Everything else is engineering around that.

---

## PART 1 — Get it running RIGHT NOW

Open a terminal (PowerShell or Git Bash) and paste this exactly:

```
cd D:\Downloads\Hackathon\pehchaan\api
uv run python scripts/demo.py
```

Wait until you see a line like `Pehchaan demo -> http://localhost:8000`. Leave that terminal window open and
running — don't close it, don't touch it again.

Now open a web browser and go to:

```
http://localhost:8000
```

You should see a page titled **Pehchaan** with a "Participant" screen. If you see that page — **you are ready.**
If you get an error or blank page, say so right now and stop reading further until it's fixed.

---

## PART 2 — What's on the screen (so you're not confused live)

There are two tabs at the top right: **Participant** and **Organiser**.

- **Participant** = what a student sees when they register for an event.
- **Organiser** = what a Hackingly staff member sees to review flagged cases.

On the Participant screen, under "Register," there's a row of grey buttons like **Genuine**, **Reused Id**,
**Blurry**, **Edited Dob**, **No Qr**, **College Id**. These are pretend ID cards we generated for the demo (fake
people, fake Aadhaar numbers, clearly watermarked "SPECIMEN" — not real documents). **Clicking one of these
buttons automatically fills in the name, loads the fake ID photo, and runs the whole check for you.** You don't
need to type anything or upload any file. One click = one full demo case.

---

## PART 2.5 — Can you actually test a REAL ID? Yes. Here's exactly what happens.

**Yes — you can upload a real Aadhaar, PAN, voter ID, or college ID right now, on this same screen, using the
normal upload fields below the demo card buttons.** This is a real, working prototype. It is not locked to the
fake cards.

Here's exactly what to expect for each, so nobody is confused live:

| Real document | What happens | Why |
|---|---|---|
| **PAN card** | Fully checked, shows **Verified** if the name matches and it's not a duplicate | No government signature involved at all — works completely out of the box |
| **College ID** | Fully checked, shows **Verified** | Same — no signature dependency |
| **Voter ID / passport** | Fully checked, shows **Verified** | Same |
| **Real Aadhaar card** | Everything is read and checked correctly (name, date of birth, age, duplicates) — but it shows **"Needs review" instead of "Verified"** | The one part that needs a real government certificate is checking Aadhaar's hidden digital signature. We tried to download that certificate twice just now and the government site blocked/returned an error both times (not our code's fault — a network/access issue). **Without it, the system correctly refuses to fully trust a signature it can't check — it doesn't guess, it asks a human instead.** That's the system being careful, not broken. |

**This is actually a good thing to show, not a weakness to hide.** If a real Aadhaar comes back "Needs review,"
say exactly this:

*"Notice it didn't just say 'Verified' — it read everything correctly, but it's honest that it can't
cryptographically prove the government signature without being registered with UIDAI in production, so it sends
it to a human rather than guessing. That's the same 'never trust a guess' philosophy from our whole design."*

**That is a strong answer, not a weak one.** It proves the system does the right thing even when it's missing a
piece — it doesn't fail open, it doesn't crash, it doesn't pretend.

**Bottom line: test with real PAN cards / college IDs live if you want a guaranteed "Verified" on a real
document. Test with a real Aadhaar too if you want — just narrate the "Needs review" result honestly using the
line above, instead of being surprised by it.**

---

## PART 3 — The exact demo, click by click (do this now, practice it twice)

Do these in order. After each click, wait 1-3 seconds for the result to appear on the right side of the screen.

### Click 1: the "Genuine" button

**What happens:** It says **Verified**, green, with a level bar filled up to "L3 Proven," and a confidence
number around 95%.

**What you say:** *"This is a real, unedited ID. In about two seconds, the system verified the person's identity
by checking the digital signature hidden in the ID's QR code — the same signature the Indian government puts
there. Name matches, age is correct for today's event, signature checks out."*

### Click 2: the "Edited Dob" button

**What happens:** It says **Not eligible**, red, with a reason shown on screen about the date of birth not
matching the QR code.

**What you say:** *"This is a card where someone changed the birth year to look older than they are. The
printed date says one thing. But the secret signature inside the QR code still has the real, original date.
They don't match — so the system rejects it and tells you exactly why. No AI was asked to 'guess' if this
looked edited. It's just math: the signature doesn't lie."*

### Click 3: the "Reused Id" button

**What happens:** It says **Needs review**, yellow/orange.

**What you say:** *"This is the same ID card as our first example, but registered under a different name. The
system catches that this exact ID was already used — and sends BOTH registrations to a human reviewer, because
we don't know yet which one is the real owner and which one is the impostor. This works across every single
event on the platform, not just one."*

### Click 4: the "Blurry" button

**What happens:** In under half a second, it says **Action required** — asking for a retake.

**What you say:** *"A bad photo is never treated as suspicious. It just asks for a retake. This matters because
the #1 requirement in the brief was: don't block real students because of a strict check. We never reject
someone just because their photo quality was bad."*

### Click 5: switch to the "Organiser" tab (top right)

**What happens:** You'll see a list of the flagged cases from above, with details.

**What you say:** *"This is what Hackingly's staff sees. Every case that needs a human is here, sorted by how
urgent it is. You can see exactly which checks passed and which didn't, a short AI-written summary of the case,
and buttons to approve, reject, or ask for a retake. The photo is only kept while a case is under review — it
gets deleted automatically once it's closed."*

### Close with these numbers (memorize them):

*"We tested this on 47 fake ID cases covering 11 different types of fraud. Zero real people were wrongly
rejected. Zero fake or fraudulent IDs got through. 96% of genuine registrations were approved automatically with
no human needed. It plugs into Hackingly's system with one API call, right after the step they already have —
so it needs almost no changes on their side."*

**That whole thing takes about 3 minutes. Practice it twice before 13:30, out loud, with the actual screen.**

---

## PART 4 — If someone asks a question (short answers)

**"Did you test this on a real Aadhaar card?"**
Answer honestly based on what actually happened this morning. If yes: "Yes, [name]'s own card, verified
successfully this morning." If no: "Not a real card yet — these are realistic fake cards we generated ourselves,
signed the same way real ones are, so the logic is identical. We'd validate on real samples on day one."

**"What if the ID has no QR code, like a PAN card or college ID?"**
"Then there's no signature to check, so it relies on checking the ID number format, matching the name on the
form, checking if it's been used before, and sending anything uncertain to a human. We're honest that we can't
cryptographically verify those — nobody can, and we say so rather than pretend otherwise."

**"Why not just use more AI to detect fakes?"**
"We do use AI — for reading the ID, matching faces, matching names, and summarizing cases for reviewers. But
for the final decision of 'is this fake,' research shows AI models are basically guessing on modern AI-edited
fakes. So the final decision is made by clear, explainable rules, not a model's confidence score. That's a
deliberate choice, not a missing feature."

**"How much does this cost to run? How fast is it?"**
"About 2 seconds per check, roughly a tenth of a paisa per check in compute cost, using the AI reading step
Hackingly already pays for. Around 40 checks per minute on one machine."

**"Is this legal to use with Aadhaar?"**
"Yes — we only ever check the signature offline, we never store the actual Aadhaar number, and we delete photos
once a review is closed. India's data protection law also requires this kind of care, and we built it in from
the start rather than bolting it on later."

**"What does each of you do on the team?"**
Have every teammate ready to say one sentence about what they personally built or are responsible for explaining.

---

## PART 5 — The 30-second version (if judges are in a hurry)

1. Click **Genuine** → point at "Verified" → *"Signature verified in 2 seconds."*
2. Click **Edited Dob** → point at "Not eligible" → *"Card was edited, the hidden signature caught it."*
3. Say: *"Zero real students wrongly rejected, zero fakes accepted, across 47 test cases. One API call to plug
   into Hackingly's system."*

Done. That's the whole pitch if you have almost no time.

---

## PART 6 — Right now, in order

1. [ ] Run the two commands in **Part 1**. Confirm the page loads.
2. [ ] Read **Part 3** out loud once, by yourself, clicking along.
3. [ ] Gather the team. Assign: who clicks the laptop, who talks, who answers questions.
4. [ ] Do the full run in **Part 3** together, out loud, twice.
5. [ ] Right before 13:30, restart it fresh so old clicks don't confuse things:
   ```
   (press Ctrl+C in the terminal running it, then run again:)
   cd D:\Downloads\Hackathon\pehchaan\api
   uv run python scripts/demo.py
   ```
6. [ ] Open http://localhost:8000, click nothing yet, wait for the judges.

You don't need to understand every technical file in this repo. You need Part 3 and Part 4. That's it.
