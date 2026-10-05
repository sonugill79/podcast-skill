# Phase Human Touch: Time to Think, Emotion and a Point of View - Decisions Document

**Created:** 2026-10-03
**Last Updated:** 2026-10-03
**Status:** All Decisions Finalized
**Related PRD:** docs/phases/phase-human-touch/phase-human-touch-requirements.md

---

## Decisions Summary

| # | Decision | Recommended | Choice | Priority | Impact |
|---|----------|-------------|--------|----------|--------|
| 1 | Sequencing | Ear test first | Ear test first | High | Renderer work waits until a rules-only A/B wins |
| 2 | Ear-test episode | Learning to sail | Learning to sail | High | Segment 3 rescripted beside the original |
| 3 | Who sets host stances | Agent picks, user can override | Agent picks, user can override | High | `stances:` in `brief.md`, announced in one line |
| 4 | Depth control | Separate `--level` + `--focus` | Separate `--level` + `--focus` | High | Two new flags, `default_level` config, angle `## Level notes` |
| 5 | Non-lexical sounds | Ban them | **QA allowlist** | High | `qa.py` treats a small set of sounds as optional; moved into v1 |
| 6 | Default pacing | Relaxed, solo stays brisk | **Relaxed everywhere** | Medium | One `default_pacing=relaxed`; `brisk` opt-in for any cast |
| 7 | pacecheck severity | Warn; agent must fix first | Warn; agent must fix first | Medium | Exit 0 + mandatory revise; `--strict` → exit 4 |
| 8 | Eval judge | Claude subagent, dev-only | Claude subagent, dev-only | Medium | `test/pacing/rubric.md` scored by a Sonnet subagent |
| 9 | Readout | Feedback-givers A/B | **Owner's ear only** | Medium | Release gated on the owner's listen, not a blind panel |

---

## Decision Details

### Decision 1: Sequencing

**Question:** Should we prove the new script rules by ear before writing any renderer code?

**Context:** The measured baselines (0 pauses in two of three episodes, only 2–4% short lines) point at the writing,
not the renderer. Building both together would hide which change helped.

**Options Considered:**
1. Ear test first: rules only, rendered with today's renderer, A/B by ear, then code.
2. Rules and renderer together: faster, but if the result misses, the cause is ambiguous.
3. Renderer first: pure code, but it targets the smaller cause.

**Choice:** Ear test first

**User modifications:** None

**Rationale:** It is the cheapest way to find out early whether the approach works, and it matches the owner's own reel plan (T1 → T2 → T3).

**Implications:**
- Milestone 1 is SKILL.md and cast rules plus one rescripted segment. No `render.py` change.
- Kill point: if the owner doesn't prefer the rescript, stop and revisit the rules before any code.
- The ear-test audio must include a few allowlisted sounds (see Decision 5) so they can be judged too.

**Effort delta:** +1 rescript-and-render step up front. It may save the whole renderer milestone.

**Status:** Decided

---

### Decision 2: Ear-test episode

**Question:** Which existing episode should we rewrite a segment of for the ear test?

**Context:** The episode needs a `sources.md` so the rescript's facts can be traced, and a weak baseline so the A/B
difference is audible.

**Options Considered:**
1. Learning to sail: learn-topic, 0 pauses, 29.2 words per line, `sources.md` present.
2. Interview prep: business content, 0 pauses. Personal content.
3. Desk chair: already the best baseline (18.8 words per line, 3 pauses), so the A/B difference would be smaller.
4. Two segments: broader, at double the work.

**Choice:** Learning to sail

**User modifications:** None

**Rationale:** It has the worst baseline, so it gives the clearest signal, and it already contains the one image that shows the mechanics working.

**Implications:**
- Rescript segment 3 ("How it actually works") to `script.humanized.txt` beside the original. Never overwrite the original.
- Render both versions to new filenames, run `qa.py` on the new one, and check every fact against `sources.md`.
- This episode lives in the private twin's episode folder, so the test runs there and nothing from it is committed to this repo.

**Effort delta:** none (this is the default path)

**Status:** Decided

---

### Decision 3: Who sets host stances

**Question:** Who decides each host's stance (point of view) for an episode?

**Context:** "No point of view" is the one feedback item the current plugin can't address at all. A badly chosen
stance costs a full re-script.

**Options Considered:**
1. Agent picks, user can override: drawn from what the research shows is genuinely contested.
2. Agent picks silently: simplest, but the listener only discovers the stances on air.
3. Always ask the user: most control, but it adds friction to every episode.

**Choice:** Agent picks, user can override

**User modifications:** None

**Rationale:** There is no friction by default, which keeps "start the research in the same breath", and a bad pick is caught before scripting.

**Implications:**
- `brief.md` gains `stances:` (one line per speaker). The agent announces them in one line after verification and before the script.
- Stances must come from contested points in `sources.md`, never from invented controversy.
- On `debate`/`panel`, the stances are the sides that already exist.

**Effort delta:** +1 brief field, +1 status line, +1 SKILL.md rule

**Status:** Decided

---

### Decision 4: Depth control

**Question:** How should listeners control depth?

**Context:** `--depth` today controls research effort only. The listener request is about how much is explained,
and about going deeper on particular aspects.

**Options Considered:**
1. Separate `--level intro|informed|expert` + `--focus` (≤ 3 aspects), keeping `--depth` for research.
2. Overload `--depth`: one knob, but quick research pitched at an expert becomes impossible.
3. `--focus` only: smallest change, but it doesn't address the beginner/expert pitch.

**Choice:** Separate `--level` + `--focus`

**User modifications:** None

**Rationale:** Research effort and explanation depth are independent axes, and real requests vary them separately.

**Implications:**
- `plugin.json` `userConfig` gains `default_level` (default `informed`).
- Every `angles/*.md` gains `## Level notes`. learn-topic's informal "starting level" maps onto `--level`.
- `--focus` gets a dedicated research agent per aspect, inside the `--depth` budget. A 4th aspect is rejected.
- A "go deeper on X" follow-up reuses `research/` and `sources.md`.

**Effort delta:** +2 flags, +1 config key, +5 angle sections, +1 follow-up flow

**Status:** Decided

---

### Decision 5: Non-lexical sounds

**Question:** What do we do about non-word sounds like "Hmm", "Mm-hm" and "Ha!", which currently fail the audio check?

**Context:** In a probe, lexical reactions ("Huh.", "Wait. In September?") passed QA at 1.00, while "Hmm. … Ha!
Mm-hm." was heard as "him" / "ha mmhm" and failed TRUNCATED and EXTRA_AUDIO.

**Options Considered:**
1. Ban them: lexical reactions only, no `qa.py` change.
2. QA allowlist: `qa.py` treats a fixed set of sounds as optional.
3. Ban now, revisit after the readout.

**Choice:** QA allowlist (this **differs from the recommendation**, which was to ban them)

**User modifications:** None (an offered option)

**Rationale:** The owner wants the natural texture that reaction sounds give a real conversation, and that is part of "sounding human".

**Implications:**
- `qa.py` gains an allowlist of non-lexical tokens (proposed: `hmm`, `mm-hm`, `uh-huh`, `huh`, `ha`) and their common
  mishearings (`him`, `mmhm`, `ha mmhm`). Allowlisted tokens are optional: not required for coverage, and not
  counted as EXTRA AUDIO.
- **Strictness is otherwise unchanged:** DROPPED, NEGATIONS, NAMES and the 0.96 coverage gate apply to every
  lexical token as before. A line made *only* of allowlisted sounds can't be reported DROPPED, so cap them in the
  writing rules (≤ 1 per segment, never a whole line on its own in the first rollout) to keep the gate meaningful.
- The ear test includes 2–3 of them to check whether Kokoro renders them acceptably. If it doesn't, the allowlist
  stays in `qa.py` but the writing rules discourage the sounds.
- pacecheck reports a count of non-lexical sounds instead of banning them.

**Effort delta:** +1 `qa.py` feature with selftests (allowlist + mishearing map); the PRD moves this from Future to v1

**Status:** Decided

---

### Decision 6: Default pacing

**Question:** Which pace should be the default once this ships?

**Context:** The "constant pace" complaint applies to every cast, but a solo news brief is the one format where
speed is the point.

**Options Considered:**
1. Relaxed, with solo staying brisk: each cast declares its own default.
2. Relaxed everywhere: one default.
3. Brisk everywhere: opt-in only.

**Choice:** Relaxed everywhere (this **differs from the recommendation**, which kept solo brisk)

**User modifications:** None

**Rationale:** One default is simpler to explain and test, and solo episodes also benefit from time to think.

**Implications:**
- `plugin.json` `userConfig` gains `default_pacing` (default `relaxed`). No per-cast pacing field.
- `--pacing brisk` reproduces the 0.2.0 gaps byte for byte, for anyone who wants the old speed (e.g. a daily brief).
- `casts/VOICES.md` "Daily news brief" guidance should mention `--pacing brisk`.

**Effort delta:** −1 cast-file field compared with the recommendation

**Status:** Decided

---

### Decision 7: pacecheck severity

**Question:** When the pace report flags a problem, should it block the render?

**Context:** The metrics are heuristics, and "Tier 0 must always work" rules out a false alarm stopping an episode.

**Options Considered:**
1. Warn, and the agent must fix first; `--strict` fails.
2. Block by default.
3. Report only.

**Choice:** Warn; agent must fix first

**User modifications:** None

**Rationale:** The rules get enforced without a heuristic false positive ever costing a listener their episode.

**Implications:**
- `render.py --dry-run` exits 0 with warnings. With `--strict` it exits 4 (3 stays reserved for "not installed").
- SKILL.md: revise every flagged segment before rendering. In a non-interactive run, render anyway and append the warnings to the `brief.md` outcome.
- The eval suite runs pacecheck with `--strict`.

**Effort delta:** none (the default path)

**Status:** Decided

---

### Decision 8: Eval judge

**Question:** What judges the subjective checks in the eval suite?

**Context:** The judged checks (felt moment per segment, earned reactions, stances and disagreement, opinions
marked, level respected) need a judge strangers can run from a clone.

**Options Considered:**
1. A Claude subagent at dev time, scoring against a rubric file.
2. A local Ollama judge: free here, but an extra install for strangers, and a weaker judge of tone.
3. Human ear only: no regression guard.

**Choice:** Claude subagent, dev-only

**User modifications:** None

**Rationale:** Anyone with Claude Code can run it, it needs no extra install, and it judges tone better.

**Implications:**
- `test/pacing/rubric.md`, plus fixture scripts for 3 angles × 3 levels, and a short runner doc saying how to have a Sonnet subagent score them as JSON.
- Go-live: ≥ 90% of fixtures pass the rubric and pacecheck `--strict`; 100% pass `qa.py` ≥ 0.96.
- It is never run inside a user's episode, so users pay no extra tokens.
- Record the suite path in `CLAUDE.md`.

**Effort delta:** +1 rubric, +9 fixtures, +1 runner doc

**Status:** Decided

---

### Decision 9: Readout

**Question:** How do we decide the release worked?

**Context:** The PRD proposed a blind A/B with ≥ 5 listeners. Recruiting them could stall the release.

**Options Considered:**
1. A blind A/B with the people who gave the feedback (3+), plus the owner.
2. The owner's ear only.
3. A blind A/B with 5+ listeners.

**Choice:** Owner's ear only (this **differs from the recommendation**, which was the feedback-givers A/B)

**User modifications:** None

**Rationale:** It is the fastest path, and the owner already holds the listener feedback in their head.

**Implications:**
- Gate 1 (Milestone 1): the owner prefers the rescripted segment. If not, stop.
- Gate 2 (release): the owner listens to one full new-style episode, plus the `--pacing brisk` version of the same
  script, and approves. Then version 0.3.0, a PR, and the owner merges.
- Risk: it tests one person's taste. Mitigation, not a gate: send the final episode informally to the original
  feedback-givers and record what they say in the phase notes.
- The PRD's Readout gate and blind-A/B metrics are rewritten to match.

**Effort delta:** −recruiting and running a blind panel

**Status:** Decided

---

## Next Steps

1. **Create implementation plan** - Run `/pm-agent plan human-touch`

---

**Status:** All decisions finalized and ready for implementation planning

## Execution decisions

### E1 (1.1) — the arc's pause is written as two directives, not `[pause 1–1.5]`
- **Problem:** the plan's [Contract] text says `[pause 1–1.5]`; `render.py`'s `\[pause ([\d.]+)\]` rejects a range, so a model copying it would write an unrenderable script.
- **Options:** copy verbatim · spell it out.
- **Choice:** "a pause of one to one and a half seconds (`[pause 1]` to `[pause 1.5]`; one number per directive)". The rule name "Arc per segment" is unchanged for the 6.1 rubric.
- **Trade-off:** wordier than the contract text.

### E2 (1.1) — "huh" is a capped sound, not a free lexical reaction
- **Problem:** the PRD (§Use Case 1, D5 prose) and the plan template list "Huh." as a preferred word, while PRD D5's allowlist, Decision 5 and the 2.1 `NONLEXICAL` contract list `huh` as a capped sound. Two sources disagree.
- **Options:** drop `huh` from `NONLEXICAL` in 2.1 · keep it capped and stop recommending a bare "Huh.".
- **Choice:** keep it capped (the code contract and the stricter reading). Preferred words become "Wait.", "Okay.", "Right." and repeat-backs; examples use "Huh. In September?".
- **Trade-off:** one fewer free reaction word. Surfaced to the owner; reversible in 2.1 by deleting one key. Ledger L5.

### E3 (1.1) — stances may rest on a judgement call when the facts are settled
- **Problem (review MEDIUM-2):** "stances only from genuinely contested points" plus "≥ 1 disagreement per episode" left no legal move on a settled learn-topic (which forbids false balance) or on solo.
- **Choice:** a stance comes from a contested point or, when the facts are settled, from a judgement call (what matters most, what to do, who it's for); disagreements are about meaning or action, never a settled fact; the disagreement rule applies to casts with ≥ 2 hosts.
- **Trade-off:** weaker "contested" requirement; the PRD's own sail example ("beginners need the physics") is a judgement call, so this matches the PRD's intent.

### E4 (1.1) — no invented experience
- **Problem (review MEDIUM-1):** "humour and vulnerability come from the host" and "one concrete image" let a model invent anecdotes ("I tried it last week…") that trace to nothing.
- **Choice:** a §4 bullet: no invented first-hand experience, anecdotes or biography; a concrete image is a verified detail or an analogy said as one. "This is the part I got wrong for years" swapped for "That's not what I'd have guessed."
- **Trade-off:** less colour; verification wins.

### E5 (1.1) — persona paragraphs reworded
- Maya's "opens each segment, asks the question" contradicted per-segment role swaps. She now opens/closes the episode, and a segment she tells ends on what it taught; each persona gained one tell/listen sentence. Temperament text kept.

### E6 (1.2): the ear test was revised once before the owner heard it
- **Problem:** the opus review of v1 failed on two counts. The turn landed mid-segment, so the arc rule wasn't actually tested. "jibe" and "Bernoulli" also tripped QA.
- **Choice:** v2 makes the no-go zone and tack/jibe the setup, so the turn and its pause come near the end. It keeps one felt moment and drops "Ha.". A local lexicon (Bernoulli, bow) fixes real Kokoro mispronunciations.
- **Trade-off:** the A/B is `seg3.original.lex.mp3` against v2, both with the lexicon, so the only variable is the script. v1 (which includes "Ha") is kept for the sound check.

### E7 (1.2): pause placement measured from the owner's read-aloud
- **Problem:** the owner's verdict on v2 was "not that much of an improvement; the pauses weren't where I'd expect".
- **Method:** the owner read v2 aloud with no pause marks (66 s used). faster-whisper word timestamps plus ffmpeg `silencedetect` (-35 dB, ≥ 0.15 s) measured every gap of 0.25 s or more. The same 135 words were measured in the Kokoro render. The recording stays outside git; only these numbers are kept.

| same 135 words | owner | v2 render | v3 render |
|---|---|---|---|
| duration | 65 s | 47 s | 54 s |
| total pause time | 24.4 s | 12.9 s | 17.6 s |
| pauses ≥ 1 s | 11 | 2 | 7 |

- **Pattern (one reader, one passage, so this is a hypothesis):**
  1. The longest beats (1.3–1.8 s) come right after a new term or a step *lands*: "no-go zone", "angle across", "each turn is a tack", "the gentle one", "slams across". v2 had 0–0.7 s there.
  2. Every sentence end gets 0.6–1.1 s. Kokoro gives ≈ 0 between sentences inside one script line, and the renderer has no syntax for a pause inside a line (L13).
  3. The owner paused less than v2 after a dramatic question: 1.15 s against v2's 1.88 s after "So how?". v2 put its silences in the wrong places.
- **v3 (script-only, no code):** one line per sentence, `[pause 1.2]` after a landing sentence, and `[pause 0.7]` at a speaker change. Single-word reactions stay attached to the next sentence; split off alone, they failed QA as DROPPED. QA: ok, 0.977, 5 whisper-only flags.
- **Implication if v3 wins:** rule 1 belongs in §4 (it is the model's job). Rule 2 belongs in the renderer as a sentence gap, which is automatic, so 3.1's gap table gains a `sentence` kind. `[pause N]` after dramatic lines should be rarer.

### E8 (1.2): owner verdict on v3, the learner role, "mm-hm", and the second read-aloud
- **Verdict (2026-10-04):** v3 is better than A ("but we may be able to do a little better"). The Decision 1 gate condition, "prefers humanized", is met.
- **Owner direction, applied to SKILL.md §4 and two-host.md:**
  - The listening host *is the learner*. They voice the audience's questions and thoughts, and check understanding by restating it as a question ("I see. So you're saying…?").
  - They add no facts, and they never use presenter lines ("So, sit with that" sounded out of character).
- **"Mm-hm" is banned.** The owner heard it spelled as letters. Confirmed from Kokoro's phonemizer:
  - "Mm-hm" → `ˌɛmˈɛmˌeɪtʃˈɛm`. Every m-spelling ("Mhm", "Mmhmm", "Mm") spells letters too.
  - "Uh-huh" → `ˈʌhˈʌ` and "Huh" → `hˈʌ` are fine.
  - **This changes the Decision 5 allowlist contract** that 2.1 (`NONLEXICAL`) and 4.1 build on: drop `mm-hm`. Ledger L14.
- **Second read-aloud (the rest of the segment, 414 words, 110 wpm with pauses).** It confirms E7 and adds two levels:

| Level | Owner pause | Where |
|---|---|---|
| micro | 0.25–0.3 s | just *before* the key word ("It's … wrong", "a … force", "where it … breaks") |
| clause | 0.4–0.8 s | commas |
| sentence | 0.6–1.2 s | every sentence end |
| landing | 1.2–1.8 s | after a new term lands or a quote ends |
| wrap | 2.1–2.7 s | a sub-topic concludes ("…no longer path", "…one force") |
| shift | ≈ 4 s | before the opinions |

- **What v4 includes, and what it can't yet:**
  - v4 adds the wrap and shift levels and longer post-quote beats, as script-only `[pause N]`.
  - The micro level needs a mid-line pause, which is renderer work (L13).
  - The owner also added "yeah", "got it", "Hmm, my read" unprompted, which supports lexical reactions plus one sound in front of words.
- **QA:** v4's NAMES flag on Alex's "Bernoulli" is whisper context. The same line rendered alone (identical cached audio) passes, and its phonemes are `bˈɜːnuːli`. Same class as L9.

### E9 (1.2): v5 was rewritten as a lesson (educator and learner), not patched
- **Owner, on v4:** "better, but the content needs to improve: a script that better represents the educator and learner."
- **v5 is a rewrite, not line edits:**
  - The learner brings the puzzle and makes the common guess before the reveal.
  - The educator teaches in small steps and asks the learner to predict.
  - The learner asks the next natural question, explains it back in his own words, and the educator confirms or refines it.
  - Same facts and the same three byte-identical quotes; one sound ("Huh").
- **Opus fact-check:** FAIL on three items, all fixed before sending.
  - "Air hitting the wing" is the impact misconception.
  - "The only thing left is forward" overstated; the keel cancels most of the sideways force.
  - "Most of the force points sideways" has no source.
  - The LOW fixes were also applied, so the learner no longer supplies facts or the Newton/Bernoulli labels.
- **Pronunciation:** the lexicon's `Bernoulli => Bernoolee` passes in context for both voices; `Bernooli` did not.
- **QA:** ok, 0.980, flags whisper-only. "Picture" was heard as "make sure"; the isolated round-trip is clean.
- **Cost:** 708 words, 4:35, against 375 words and 2:14 for the original segment. **If v5 wins, the rule set needs a "lesson shape" for learn-topic, and the budget line (3.2) must absorb roughly ×1.9 words per fact.**

### E10 (1.2 close): the lesson shape and the measured pause ladder are now rules
- **Owner, on v5:** "much better, write it into the rules".
- **§4 gains "Teach, don't present":** the learner's puzzle opens the segment; the educator asks for a guess before the reveal; one idea per educator turn; once per segment the learner explains it back; the learner never supplies a fact or term first; the segment ends by answering the opening puzzle; the budget is about ×2 words per fact.
- **"Room to think" now carries the measured ladder (E7/E8):**
  - one sentence per line;
  - 1.2 s after a landing, 1.5 s after a quote, 2 s at a wrap, 2.5 s before opinions, 0.7 s at a speaker change;
  - no long silence after a question;
  - this replaces "[pause 2] after a question to the audience", which the owner's reads contradicted.
- **two-host.md Roles:** the teller is the educator and the listener is the learner.

### E11 (post-1.2): owner reading Alex's six reaction lines, compared with Kokoro (am_michael), and what Kokoro can be made to do
- **Measurement:** faster-whisper word boxes trimmed by energy, plus an autocorrelation pitch track. The pitch numbers are approximate (octave errors); durations and gaps are reliable.

| Owner does | Owner | Kokoro |
|---|---|---|
| Holds the word just *before* the hard part ("so there's… no longer path", "and… it still lifts", "then I… just… slide") | 0.5–1.2 s | 0.1–0.25 s |
| Thinking beat after an interjection ("Wait,", "Huh,") | 0.75–0.85 s | ≈ 0.25 s |
| Key word longer, with a pitch move ("lifts" rising, "squeezed" falling, "sail pulls") | ≈ 2× | baseline |
| Melodic range (p10–p90) | 11.2 st | 8.1 st |
| Question ending ("…just wrong?") | rises | falls; whisper transcribes it as "wrong." |

- **Kokoro control probe (kokoro_onnx, same line):**
  - Ellipsis after the hesitation word lengthens it (0.24 → 0.43 s) and adds ≈ 0.4 s. A partial win, and free.
  - Ellipsis or a dash after "Wait" does nothing (0.26 → 0.30 s).
  - Extra `ː` in the phonemes: no useful effect.
  - `speed 0.85` slows everything evenly, not the word.
- **Conclusion:** timing (beats, holds) is reachable with a mid-line beat and word-level time-stretch in the renderer. Pitch (rising questions, a wider melody) is not reachable with Kokoro. That needs an expressive engine or pitch post-processing. Owner decision pending (L17).

### E12 (proposal, not decided): an optional expressive-voice upgrade tier
- **Owner:** wants to pursue an expressive engine, and asked whether it works for strangers. It does if it is opt-in, sized and announced, and falls back to Kokoro (the existing tier model).
- **Research (opus sub-agent, primary sources; nothing installed, not yet re-verified by the orchestrator):**
  - No local engine offers per-word pitch or emphasis control. What exists: an emotion intensity knob, inline tags, per-line natural-language style, reference-audio transfer, and speech-to-speech conversion.
  - **Chatterbox (MIT/MIT)** is the recommended first tier.
    - One codebase runs on NVIDIA, Apple Silicon (MPS) and CPU (the Nano model).
    - Weights are about 3 GB plus torch.
    - It has a per-line `exaggeration` knob or `[laugh]` tags.
    - It ships ChatterboxVC (speech-to-speech), which re-voices an owner recording as a host.
    - Every output carries an always-on Perth watermark, which must be disclosed.
    - It needs its own venv (pinned torch/transformers).
  - **VoxCPM2 (Apache/Apache, about 5 GB)** for a GPU-only "studio" tier: a fixed host clip plus a per-line style prefix ("(doubtful, slower)").
  - **Qwen3-TTS (Apache)** as an alternative; its only native English presets are male.
  - **IndexTTS2 (custom bilibili licence)** only behind an explicit licence acceptance.
  - **Disqualified for the default:** non-commercial weights (F5-TTS, MaskGCT/Vevo, Spark-TTS, OmniVoice, Fish/OpenAudio, Higgs v3), VibeVoice (code withdrawn), and engines needing espeak-ng or stale (StyleTTS2, Zonos).
- **Hosts need reference clips** on cloning engines. Ship synthetic, licence-clean clips (for example rendered from Kokoro), never a real person's voice.
- **Proposed next step:** a local prototype of Chatterbox in a scratch venv, outside the plugin and the state dir, rendering v5 for an A/B against Kokoro. No shipped change until the owner hears it. This would be a new milestone; it is not in the original plan.

### E13 (X1): bake-off results, before the owner's listen
- **Setup:** the v6 segment was rendered by Kokoro, Chatterbox (original and Turbo), VoxCPM2 and Qwen3-TTS-1.7B-Base. Host clones came from Kokoro reference clips, so they are licence-clean and the hosts stay recognisable. Engines ran in scratch venvs on one GPU. Nothing was installed into the plugin.

| Engine | Size (venv + weights) | Speed (×real time) | VRAM | QA coverage | Pitch range (6 lines) | Questions rise? |
|---|---|---|---|---|---|---|
| Kokoro | (installed) | 0.12 CPU | n/a | 0.978 | 8.0 st | no, falls on all |
| Chatterbox | 6.5 + 3.0 GB | 0.36 | ≈ 4.5 GB | 0.980 *with a per-chunk whisper check and retry*; 0.952 without, dropping a whole quote | 12.4 st | **yes** |
| Chatterbox Turbo | + 3.8 GB | 0.17 | ≈ 3.8 GB | 0.972 | 9.2 st | flattest of the new engines |
| VoxCPM2 | 7.0 + 4.7 GB | 0.40 | ≈ 7.5 GB | 0.986 | 11.7 st | mixed |
| Qwen3-TTS Base | 6.5 + 4.3 GB | 0.60 | ≈ 6.6 GB | 0.989 | 11.4 st | mixed |

- **ChatterboxVC on the owner's reading:**
  - it keeps the owner's timing and pitch contour (r = 0.80);
  - speaker similarity to ALEX is 0.905;
  - speed 0.11 × real time.
- **Chatterbox's watermark** survives MP3 encoding (detector reads 1.0).
- **Implications for a shipped tier:**
  - Chatterbox needs a per-chunk check-and-retry loop (whisper) inside the renderer, not just end-of-episode QA.
  - All three need about 10–12 GB of disk and an NVIDIA GPU (or a slow Mac) to be practical.
- The owner's verdict is pending.

### E14 (X1 close): Qwen3-TTS becomes its own phase; Human Touch ships first
- **Owner pick (2026-10-04):** Qwen3-TTS and "your voice as Alex" (ChatterboxVC) sounded best.
- **Decision (owner approved):**
  1. Human Touch ships first, on Kokoro: rules, timing, beats, pacing, level/focus, eval and 0.3.0. No engine change in this phase.
  2. Next phase, "Expressive Voice": an opt-in `upgrade voice-expressive` on Qwen3-TTS-1.7B-Base.
     - Hosts cloned from Kokoro reference clips.
     - Size stated first (≈ 11 GB). Offered on NVIDIA ≥ 8 GB; Apple Silicon after a test.
     - Kokoro as fallback; QA stays the hard gate.
  3. Voice conversion (the owner records key reaction lines; ChatterboxVC re-voices them as the host) is a personal experiment in the private pipeline only, not a plugin feature: it needs a human read per episode and a second engine stack.
- **Housekeeping:**
  - The bake-off venvs, weights and caches (43 GB, scratch) were deleted with the owner's approval.
  - The audio, README and driver scripts stay in the private twin's `ear-test/bakeoff/`.

### E15: rules review of the post-1.1 changes (FAIL, 1 HIGH + 5 MEDIUM) → fixed
- **HIGH: "one sentence per line" and "15–30% of lines ≤ 6 words" contradicted each other.**
  - The reviewer read v6 in its turn form. The *rendered* v6 was one sentence per line, but only because of an orchestrator formatter, not the model's writing.
  - **Choice:** the model writes natural turns of at most three short sentences. Sentence and turn gaps become renderer behaviour under `relaxed` (3.1, ledger L22). The length rule counts sentences.
  - **Trade-off:** §4 describes renderer behaviour that lands in 3.1. Nothing ships before then.
- **MEDIUMs fixed:**
  - No `[pause 0.7]` at every speaker change; the renderer owns that gap.
  - Teach/Roles are scoped to explanatory two-host segments. Argument and verdict segments use Stance; panel and solo use their cast files (L23).
  - two-host's description no longer gives Alex the detail permanently.
  - Stakes come first, then the learner's puzzle.
  - The wrong guess must be a misconception recorded in `sources.md` ("I don't know" otherwise). A restatement the educator confirms must match the sources, and the educator corrects any overstatement. This closes the route behind E9's overstatement.
- **LOWs fixed:**
  - Cold open and wrap are exempt from the quotas.
  - The ladder is its own bullet.
  - One-word reactions lead into a sentence.
  - No inline pause inside a quote.
  - What to cut when words run short.
  - Three-sentence turn limit in both files.
  - The arc points at the ladder.
- **Added from v6:** the "park the big question" move, and naming where the analogy breaks.

### E16 (2.1): the short-sentence band follows the scripts the owner approved, not the PRD
- **Problem:** the PRD Script Rules row 7 says 15–30% of lines should be six words or fewer, and E15 said "one in four".
  - pacecheck measured *sentences*: the owner-rejected original segment 3 sits at 29–32%, and every owner-preferred version (v2–v6) at 56–60%.
  - The PRD band would flag all approved scripts and pass the rejected one.
- **Options:** keep the PRD band · move the band to the measured preference.
- **Choice:** `FLAT_LINES_BAND = (0.40, 0.70)`, and §4 says "about half", backed by the owner's verdicts (1.2, E8–E10).
  - This deliberately supersedes the PRD row. The PRD and decisions doc are out of sync on this one number until 6.2 updates the PRD.
  - The PRD's "avg ≤ 22, sd ≥ 8" line targets also fail on preferred scripts. They are printed only, not warned.
- **Trade-off:** the share is a floor, not a quality signal; v2 and v5 score alike.
- **Results:** original segment 3 → NO_PAUSE + FLAT_LINES (`--strict` exit 4); v6 → clean.

### E17 (3.1 brief): `relaxed` is defined as "reproduce the owner-approved v6", not by the plan's sketch values
- **Problem:** the plan's GAPS values ([Sketch]) predate the owner's measurements. The approved v6 audio came from a script formatter that splits sentences and puts 0.7 s at speaker changes (E15, L22).
- **Choice:**
  - `relaxed` = renderer-side sentence splitting with the formatter's exact rules, a 0.32 s same-speaker gap and a 0.7 s handoff.
  - Acceptance: `relaxed` on the turn-form `v6.turns.txt` must be PCM-identical to the approved v6 render.
  - `brisk` stays PCM-identical to main/0.2.0.
  - A `sentence` kind is added to the GAPS contract (additive).
- **Trade-off:**
  - Splitting means brisk → relaxed re-synthesises an existing episode's lines once (new chunk texts). The plan's "changing pacing re-synthesises 0 lines" holds only between relaxed and spacious.
  - Hostile-env row 6 changes to match. Accepted: sentence-level synthesis is what the owner approved by ear.

### E18 (6.1): the judged eval exposed fact overreach; fixed by a self-check rule, then a majority-of-3 judge
- **Problem:** the first Sonnet judge run scored 0/10 fixtures clean (79% of rows).
  - The script-writing model added unverified scope and detail ("a grocery chain", "near people's homes", "for most", "every trip"), let the learner supply details first, and left judgements unmarked.
  - These are exactly the defects "verification is the product" exists to stop.
- **Choice:** do not hand-polish fixtures to the rubric. Instead, fix the *rule*:
  - SKILL.md §4 gains a mandatory line-by-line **self-check against `sources.md`** before the dry-run: Verified-only substance, estimates as estimates, derived numbers as arithmetic, no recap that joins two rows, learner guesses only from recorded misconceptions, terms explained at level, image and line per segment.
  - The fixtures were then rewritten by following that step.
  - The cast's fixed opening line is exempted from no-invented-experience (it refers to the episode's own research).
- **Results:**

  | Run | Fixtures clean | Rows passing |
  |---|---|---|
  | 1 | 0/10 | 79% |
  | 2 | 6/10 | 96% |
  | 3 | 4/10 | 94% |

  - Each strict judge finds different fine-grained overreach, so single runs are noisy.
- **Gate method:** Decision 8's threshold is unchanged (≥ 90% of fixtures pass every row), scored by three independent Sonnet judges with a per-row majority, so one judge's idiosyncrasy can't pass or fail a fixture.
- **Trade-off:** the gate costs about 3× tokens at dev time, and nothing at user time.

### E19 (6.2 release listen): fixed roles — Maya always teaches, Alex always learns
- **Owner, on the release episode (2026-10-05):** likes `relaxed`, but "the narrators are switching seats … really odd. If Alex is the learner, he should stay the learner the entire way through."
- **Choice:** the per-segment swap (from the PRD Script Rules and 1.1) is replaced by fixed roles.
  - two-host: Maya is the educator and Alex the learner for the whole episode.
  - §4 Roles, two-host personas, Roles, Stance and Writing are rewritten.
- **Consequences:**
  - pacecheck's SAME_TELLER must invert: warn when the teller *changes* on a two-host cast.
  - The two-host fixtures (written with swaps) must be rewritten and re-judged.
  - The release episode must be re-scripted.
- **Supersedes:** PRD Script Rules row 1 ("swap between segments") and E10's swap wording.

### E20: owner picks Qwen ("variant B") over recording their own lines
- **Style test (2026-10-05):**
  - Copying the owner's delivery onto lines they never recorded reached pitch-contour r ≈ 0.2–0.3, no better than plain Qwen.
  - Only their real reading, voice-converted, carried it (r = 0.82).
- **Owner:** "Use B, since me recording podcasts isn't scalable."
- **Choice:**
  - Qwen3-TTS as Alex (and Maya) is the target of the Expressive Voice phase.
  - The release2 episode is rendered with Qwen as a preview.
  - Human Touch 0.3.0 still ships on Kokoro (E14).
  - Voice conversion of the owner's recordings is dropped, even as a private experiment.
- **Housekeeping:** the scratch style/ installs (39 GB) are kept until the Qwen preview is approved, then deleted.

### E21: owner approves the Qwen voice direction
- **Owner, on the fixed-roles episode rendered with Qwen3-TTS (2026-10-05):** "yes this sounds better."
- **Measured on this episode:**
  - Alex's questions rising: 17/35 with Qwen, against 3/35 on Kokoro.
  - Alex's pitch range: 10.2 st against 8.0.
  - QA 0.984 with zero retries; render speed 0.67× real time on one GPU.
- **Inputs for the Expressive Voice phase:**
  - Qwen3-TTS-1.7B-Base with Kokoro-derived host reference clips.
  - The plugin's timing (`plan_assembly`) reused unchanged.
  - A per-chunk whisper check with retries.
  - Qwen-specific lexicon: the owner's name needs no respelling; RYA and ASA spelled out.
- **Still pending:** the owner's explicit approval to release Human Touch 0.3.0 (Kokoro, fixed roles, relaxed).
