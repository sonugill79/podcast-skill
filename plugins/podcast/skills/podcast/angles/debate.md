# Angle: debate

**Use when** the listener wants a live disagreement argued properly: a contested question where serious people
hold opposite positions, and a one-voice summary would flatten the thing worth hearing.
**Listener goal:** hear the strongest real case on each side, from the people who actually make it, and come
away knowing which parts are settled, which are genuinely open, and where the evidence currently points.
**Cast:** `panel` (HOST / ADVOCATE / SKEPTIC). This angle assumes three voices — see `casts/panel.md`.

## Brief (ask only if missing)
- **The question, stated so it can be answered yes or no**, or as a choice between two named options. "Is X
  worth it" beats "tell me about X" — a debate needs a proposition, not a topic.
- Whether the listener has a stake in the answer (a decision they're making) or is exploring. A stake shifts
  the closing segment from "where the evidence points" to "what you should do".
- Any position they already lean toward, so the research can be told to attack it hardest.

## Research areas (one agent each)
| # | Area | Focus |
|---|---|---|
| 1 | **The case FOR, at full strength** | Build the strongest version of the affirmative — the one its most credible proponents actually argue. Named people and organisations, their real words, the evidence they cite. Never a summary of "supporters say"; find who says it and what they said |
| 2 | **The case AGAINST, at full strength** | The same, mirrored. The most serious objection, from the most credible objector — not the easiest one to knock down |
| 3 | Common ground & the settled facts | What both sides accept: definitions, numbers, timelines, the record. This is the floor the debate stands on, and it keeps the episode from arguing about facts instead of about the question |
| 4 | The evidence itself | The actual studies, filings, datasets or primary documents both sides point at. What each one measured, its sample, its date, its funding, what it does **not** show |
| 5 | Where the disagreement really is | Is it about facts, about values, or about what counts as acceptable risk? Most durable disagreements are not factual, and naming that is the most useful thing the episode does |

Run 1 and 2 **as separate agents with no knowledge of each other's output** — each is told to make its side as
strong as it honestly can. Merging them afterwards is the point: an argument written by one agent playing both
parts converges into mush.

`quick` depth merges 3+4 and keeps 1, 2 and 5 (3 agents). Never drop 1 or 2 — they are the episode.

## Segment outline (≈ share of runtime)
1. HOST: the question, why it is live now, and what would change if it were settled (8%)
2. HOST: the common ground — what nobody in this argument disputes (10%)
3. ADVOCATE: the case for, uninterrupted, at full strength (18%)
4. SKEPTIC: the case against, uninterrupted, at full strength (18%)
5. Cross-examination: they go at each other directly, host only steering (22%)
6. HOST presses both: the weakest link in each case, named (12%)
7. HOST: where the disagreement actually lives — fact, value, or risk tolerance (7%)
8. HOST: where the evidence points today, what would change it, and what could not be verified (5%)

## Must verify yourself
- **Every position is attributed to someone who holds it.** A claim of the form "critics argue…" with no
  named critic behind it does not go in the script.
- Every quote, with `rawfetch.py --grep` against the real page — both sides, equally.
- The evidence each side leans on: that the study/filing/dataset exists, its date, and that it says what the
  side claims it says. A misread study is the most common way this format goes wrong.
- Whether a named proponent still holds the position. People change their minds; a 2019 quote presented as a
  current stance is a misrepresentation.

## Don'ts
- **No invented opposition.** If the research cannot find a credible case against, the honest episode says the
  question is more settled than it looked — and switches to `learn-topic` rather than manufacturing a fight.
- **No false balance.** Equal airtime is a starting layout, not a promise. When the evidence is lopsided, the
  host says so in segment 8. Two sides does not mean two equally good sides.
- No strawmanning by ventriloquism: neither speaker gets to characterise the other's position, only their own.
- No manufactured heat. They disagree about the question, not about each other. No interrupting to score, no
  sarcasm at a person.
- Don't let the host win the debate. The host presses, names the weak links, and reports where the evidence
  points — but does not smuggle in a third position of their own.
