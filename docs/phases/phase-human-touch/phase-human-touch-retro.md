# Phase Human Touch: Retro

**Shipped:** 0.3.0 (pending the owner's push go-ahead) · **Dates:** 2026-10-03 → 2026-10-05 · **Tier:** Lightweight, serial

## Outcome
- Owner verdicts:
  - The ear test went A → v2 ("not much better") → v3/v4 (better) → v5 ("much better") → v6.
  - On the release, fixed roles plus `relaxed` was approved.
  - For the next phase, the Qwen voices were judged "sounds better".
- Measured:
  - pacecheck flags the rejected style and passes the approved one.
  - `relaxed` reproduces the approved v6 audio sample for sample; `brisk` matches 0.2.0 sample for sample.
  - The judged eval passed 10/10 fixtures by three-judge majority before fixed roles, and 9/10 after the rewrite, with the one majority finding fixed.

## What worked
- **Ear before code (Decision 1).** Four script-only rounds settled what "human" means before any renderer work.
- **Measuring the owner's own read-aloud.** It turned "the pauses are in the wrong place" into a ladder of numbers, and found the real cause: no pause inside a line was possible.
- **PCM identity as an acceptance test.** "relaxed(turn form) == approved v6" and "brisk == 0.2.0" made two big renderer changes safe.
- **Hostile review on every milestone.** Every code milestone failed its first review on a real defect. Examples:
  - the assembly loop was untested;
  - the episode-level pause rate hid a bad segment;
  - lexicon rules were lost across sentence splits;
  - a name could pass the NAMES gate disguised as a sound;
  - a stance override could bring in an unverified claim;
  - `--personal` sources leaked into "go deeper".
- **stranger.sh at release** caught an upstream PyAV 19 break that affects every fresh install, including 0.2.0.

## What didn't
- **The PRD's script rules were wrong in three places** (role swap, short-line band, pause after a question). Only the owner's ear found it, and the swap only on the full-length episode.
- **The judged eval took 5+ rounds.** A strict judge keeps finding small scope creep the writer adds. A single judge is noisy; a three-judge majority settled it. The real fix was a rule: the §4 self-check.
- **Whisper-base noise.** Homophones and window drops cost many isolation round-trips. One full-episode QA failure (L38) is a transcriber artifact that would block a user.
- **The orchestrator leaked a personal name into a phase doc.** The privacy grep caught it before any push; it will be squash-merged away.
- **Tier 0's budget estimate** started 7–21% wrong (an old WPM). It took a chunk-overhead model to get within 4%.

## Lessons to carry (agnostic; upstream to the phase-gates skill)
1. For quality that has to be heard, run owner-judged A/Bs **before** code, and keep re-running them at full length: segment-level tests missed the role-swap problem.
2. Use PCM/byte identity against the approved artifact as the acceptance test for any rendering refactor.
3. Judge LLM-written fixtures with a **majority of three**, not one judge, and fix the *rule* rather than polishing the fixtures.
4. Run the stranger/fresh-install test at every release. Unpinned transitive dependencies break silently.
