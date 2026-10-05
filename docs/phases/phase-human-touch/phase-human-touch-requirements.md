# Phase Human Touch: Time to Think, Emotion and a Point of View - Requirements Document

**Created:** 2026-10-03
**Last Updated:** 2026-10-03 (v3: reconciled with the decisions doc)
**Status:** Requirements Finalized, reconciled with decisions (see `phase-human-touch-decisions.md`)
**Related:** docs/phases/phase-human-touch/phase-human-touch-implementation-plan.md (not yet written)

---

## Problem Statement

**What problem does this feature solve?**

Listener feedback on shipped episodes (plugin 0.2.0), in the listeners' words where we have them:

- **No time to think.** Episodes move "at a constant pace where it feels like nobody has the time to actually think
  about what they're hearing". The hand-offs come quickly, with none of the natural pauses that would let an idea land.
- **No emotion.** "There isn't a whole lot of emotion." The hosts never sound as if anything matters to them.
- **No point of view.** "You don't feel like you're getting a point of view from the podcasters." The hosts relay
  sources but never say what they think.
- **Too general.** Some aspects deserve more detail. Listeners want to set how deep the analysis goes instead of
  getting one fixed pitch.

**Diagnosis:** our hosts are **two narrators taking turns**, not **a teller and a listener**. Every line carries new
information at about the same length, followed by the same gap. Nothing is felt, held back, repeated or reacted to,
so the listener never gets a beat to think. (The evidence is under Verified Facts.)

**Who is affected?** Every listener of every episode, because this is the plugin's default output. learn-topic
suffers most from pace, interview-prep and diligence from flat affect, and every angle from the fixed depth.

**What happens if we don't solve this?** The research and verification are the expensive, differentiated part of the
plugin, and they are wasted if the listener can't retain the result. Episodes are heard once and not forwarded.

---

## Background / Inspiration

### Prior art: how a person tells a story out loud
The model is a 2½-minute clip of a former NFL quarterback telling a podcast host about the hardest hit he ever took.
It was broken down line by line from its transcript. The mechanics survive in text, which matters because our
voice engine can't act. Everything has to be carried by **words, rhythm and silence**.

| # | Mechanic | In the clip | What `/podcast` does today |
|---|---|---|---|
| 1 | **Feeling before fact** | "Still makes me a little nervous to tell this story." | Opens on a fact or a number. Nothing is felt. |
| 2 | **Character before event**, which delays the payoff | Stops the play to describe the defender | Facts arrive in logical order and nothing is held back |
| 3 | **Slows down before the turn**: short sentences, one beat each | "I take a three-step drop. I throw a little slant…" | Lines are about 29 words long, and the rhythm never changes |
| 4 | **The turn lands in a short line** | "…and then everything just went dark." | The big fact is buried mid-sentence |
| 5 | **Concrete, sensory images** | "All I see is this beard." | Mostly abstract claims. In one episode the single concrete image (a watermelon seed) was the best line |
| 6 | **Deliberate repetition** | "went dark" → "everything goes black" | Each point is said once, then the script moves on |
| 7 | **Interprets his own reaction**, which is a point of view | "That might not seem that aggressive, but I thought he really meant it." | Relays sources ("Quote…") and never says "here's what I think it means" |
| 8 | **Puts the listener in the decision**, then holds a beat | "In this moment, I had to make a decision here." | Never asks the listener anything, and never leaves room to answer |
| 9 | **The payoff is his own weakness** | "Man, I'm somebody's child." | Hosts are always composed. They never admit surprise, confusion or a wrong first guess |
| 10 | **The co-host reacts as the audience**, then a coda | Laughter, "That's good"; then the after-game scene | Neither host reacts as a listener would. A fixed 0.32 s gap follows every line |

**Don't copy** the clip's content. It includes a demeaning comparison and stigmatising language about a mental-health
diagnosis. The mechanics work without them, and the cast rules must not reproduce that kind of framing.

- **Other prior art:** NotebookLM-style audio overviews show the two-host format working, and also its failure mode:
  enthusiasm that never stops, with no breathing room. "Earned, not performed" is the guard against that.
- **Analogies:** a good lecture leaves white space after a key point, and a script does the same in time. Depth is a
  zoom lens: the same subject at a different focal length.
- **References:** `casts/README.md` (Kokoro has no prosody control), `casts/two-host.md` (the current "no wow" rule
  and the fixed "Maya asks, Alex answers" rhythm), `scripts/render.py` (gap constants), `SKILL.md` §Invocation (the
  current `--depth`).
- **Relationship to the private twin pipeline:** these rules are being piloted on the private twin first and judged
  by ear. This phase is the public port, plus the level and focus axis. Nothing here is pushed without the owner's
  explicit go-ahead.
- **Note:** `CLAUDE.md` says to read `PLAN.md` first, but no `PLAN.md` exists in the repo. This PRD was written from
  the code, casts and angles directly.

---

## Verified Facts & Assumptions

### Verified
| Claim | How verified | Date |
|-------|--------------|------|
| **Pauses are almost never written.** Three production scripts contain 0, 0 and 3 `[pause]` lines, across 53 to 107 speaker lines each | `awk` count over each `script.txt` | 2026-10-03 |
| **Line length never varies.** Average words per line is 29.2, 29.2 and 18.8, and only **2–4%** of lines are 6 words or shorter | Same `awk` pass | 2026-10-03 |
| **Every turn has the same gap**: a fixed 0.32 s, and 1.1 s at `---`, whoever speaks next and whatever was just said | `render.py:54`; `estimate_seconds()` | 2026-10-03 |
| `[pause N]` already exists and renders. The gap between what the format supports and what scripts use is a writing problem, not a renderer one | `render.py` parser (the `[pause ([\d.]+)]` branch) | 2026-10-03 |
| Speech runs at about 158 wpm net of gaps. `SKILL.md` still budgets **minutes × 153**, a stale constant | `render.py:55-61` vs `SKILL.md` §4 | 2026-10-03 |
| `--depth` only controls **research effort** (agents, claims, a reviewer). Nothing in the script changes with it | `SKILL.md` §Invocation; `grep -i depth scripts/*` | 2026-10-03 |
| learn-topic informally asks for a "starting level". No other angle does | `angles/learn-topic.md` §Brief | 2026-10-03 |
| The default cast **forbids** reaction ("no wow") and fixes the roles: Maya asks, Alex answers | `casts/two-host.md` | 2026-10-03 |
| **Punctuation changes Kokoro's timing.** The same 15 words took 4.30 s plain and 5.23 s with an ellipsis and an em-dash (+22%). This is timing, not emotion: it creates a hesitation but does not make the voice sound nervous | Probe render with `--cast casts/two-host.md --no-rotate`, measured with `ffprobe` | 2026-10-03 |
| **Lexical reactions pass QA; non-lexical sounds don't.** "Wait. In September?" / "In September." / "Huh. I'd have guessed the opposite." / "Honestly, this one surprised me." scored coverage 1.00 with 0 flags. "Hmm. … Ha! Mm-hm." was heard as "him" and "ha mmhm", and failed TRUNCATED and EXTRA_AUDIO | Two probe renders plus `qa.py` (both were below the 150-token gate floor, so coverage was informational, but the per-line checks ran) | 2026-10-03 |
| Gaps are not in the TTS cache key, so changing them never re-synthesises audio | `render.py` `cache_key()` signature | 2026-10-03 |

### Assumed
| Assumption | What would invalidate it | Tested by |
|------------|--------------------------|-----------|
| Most of the human feel comes from the **script rules** (roles, beats, stance). The gap table helps but isn't sufficient alone | A rescripted segment rendered with the fixed gap sounds no better than the original | Milestone 1.2, prove by ear |
| Explicit opinions, labelled as opinions, don't erode trust in verified facts | Listeners can't tell opinion from fact, or a judged eval finds opinions phrased as facts | Milestone 1.2 listen; 6.1 judged eval |
| Reaction and recap lines cost about 10–15% of the word budget, and a fixed `--minutes` absorbs that by covering slightly less | A fixture episode drops an angle's must-verify claim to fit | 6.1 fixtures |
| One word (intro / informed / expert) is enough to re-pitch a script | Listeners say the level was "wrong" | Readout |
| A named `--focus` meets the "more detail" request better than making every episode longer | Listeners ask for longer episodes across the board | Readout |
| Kokoro renders a short reaction line (1–5 words) with acceptable intonation | A listen finds "Wait. In September?" sounds flat or robotic | Milestone 1.2 |

---

## Goals & Success Metrics

### Primary Goals
1. **Time to think.** Every key idea gets a beat to land (a pause, a reaction, a recap or a question to the listener)
   before the next one arrives, and line length varies.
2. **Emotion, earned.** Hosts say how they feel, admit surprise or a wrong first guess, and react as the audience
   would, but only in response to something verified. Nothing is performed.
3. **A point of view.** Each host holds a stance, interprets what the facts mean, and disagrees at least once. The
   disagreement is not always resolved. Opinions are marked as opinions, and facts still trace to `sources.md`.
4. **Adjustable depth.** The listener chooses the level and named focus areas, separately from how much research
   is done.
5. **No regression on the non-negotiables.** Tier 0 works with nothing installed, and verification and QA keep their
   current strictness.

### Quantitative Metrics
| Metric | Current Baseline | Target | How to Measure |
|--------|-----------------|--------|----------------|
| `[pause]` lines per 90 s of script | ≈ 0 (0, 0 and 3 per episode) | ≥ 1, and no segment over 3 min without one | `pacecheck` |
| Share of speaker lines ≤ 6 words | 2–4% | 15–30% | `pacecheck` |
| Average words per line | 29.2 / 29.2 / 18.8 | ≤ 22, with variance (stdev ≥ 8) | `pacecheck` |
| Longest single-speaker run | 51 / 60 / 61 words (pacecheck, 2026-10-04, 3 production scripts; ear test: 41 → 45) | ≤ 90 words outside `solo` | `pacecheck` |
| Felt moments per segment | ≈ 0 | ≥ 1 | judged eval (6.1) |
| Host disagreements per episode | ≈ 0 | ≥ 1, with ≥ 1 per 3 episodes left unresolved | judged eval |
| Opinions phrased as fact | not measured | 0 | judged eval |
| Allowlisted non-lexical sounds per segment | 0 | ≤ 1, never a whole line on its own | `pacecheck` (Decision 5) |
| Mean inter-turn silence | 0.32 s, fixed | 0.45–0.7 s, varying by context | render events |
| QA coverage, full episode | ≥ 0.96 | ≥ 0.96, unchanged | `qa.py` |
| Owner A/B by ear (Milestone 1.2) | N/A | new segment preferred | owner listen |
| Owner release listen (Readout) | N/A | owner approves one full new-style episode over its `--pacing brisk` version on "had time to think", "sounded human" and "knew what they thought" | readout (Decision 9) |

### Qualitative Metrics
- After one listen, a listener can repeat back the line each segment wanted remembered.
- Listeners can say which host thought what.
- Nobody describes the hosts as "reading at each other" or as "hyped".

---

## Overview

This phase changes how a verified script is **written and timed**, not how it is researched. It does four things:
ten storytelling mechanics become script rules (see Script Rules Architecture), each episode gets a stance per host
(see Point-of-View Architecture), the renderer uses context-aware gaps and a pacing report (see Pacing
Architecture), and a level and focus axis is added that is distinct from research `--depth` (see Depth
Architecture). Rules first, proved by ear, then code.

**Key Principle:** Write a teller and a listener, not two narrators. The listener's attention is the scarce
resource, so spend words on helping an idea land.

---

## Core Concept

**Current State:** Hosts alternate in fixed roles, with lines of about 29 words and a uniform 0.32 s gap. Pauses are
supported but unused. Reactions are banned. Hosts relay sources without saying what they think. Depth changes the
research but not the explanation.

**Desired State:** In each segment one host tells and the other listens, and the roles swap. A segment follows a
story arc: stakes, setup, slow-down, a short line for the turn, a pause, a reaction, a coda. Each host has a stance
recorded in the brief, says what a fact means to them, and they disagree. Line lengths vary, silence follows the
things worth thinking about, and the listener chooses how deep the episode goes.

---

## User Experience Flow

### Use Case 1: A default episode, now human
**Scenario:** A user asks for a learn-topic episode with no new flags.

**Flow:**
1. User: `/podcast how sailboats sail upwind`
2. The brief records `level: informed`, `pacing: relaxed`, and **a stance per host**, for example
   "Maya: sceptical that beginners need the physics; Alex: thinks the physics is the whole point".
3. The script follows the arc for each segment, with teller and listener roles swapping between segments.
4. `render.py --dry-run` prints pacecheck. The agent revises any flagged segment before rendering.
5. Render with context-aware gaps. QA runs as before.

**Example Output (one segment, Alex telling, Maya listening):**
```
# ── 3. How a sail pulls you into the wind ─────
ALEX: This is the part I got wrong for years.
ALEX: Picture a watermelon seed, squeezed between two fingers.
MAYA: Okay.
ALEX: Squeeze, and it shoots out sideways. Fast.
ALEX: The wind pushes on the sail. The keel pushes back on the water.
ALEX: The boat is the seed.
[pause 1.2]
MAYA: Wait. So it isn't being pushed. It's being squeezed forward.
ALEX: Squeezed forward. That's it.
MAYA: Honestly? I'm not sure a beginner needs this. You can sail fine without it.
ALEX: I think that's where people stall, though. They can't tell why the boat stopped.
[pause 0.8]
MAYA: So, sit with that. The boat is the seed.
```
_Mechanics used: feeling before fact (1), a concrete image (5), slow-down in short lines (3), the turn in a short
line (4), a pause, the listener reacting as the audience (10), a stance and disagreement (7), and repetition of the
line to remember (6)._

**Example Output (dry-run pacecheck):**
```
pacecheck  level=informed  pacing=relaxed  est 19.4 min (target 20)
  lines ≤6 words 22%   avg 17.3 (sd 10.1)   longest run ALEX 74 words (L88)
  pauses 14 (1 per 83 s)   ⚠ segment 5 "Where it is now": no pause in 3.4 min
  roles  seg1 M→A  seg2 A→M  seg3 A→M ⚠ same teller as seg2
```

**Success Criteria:**
- pacecheck meets every target in Goals, or each warning is resolved before rendering.
- `qa.py` passes at ≥ 0.96.
- Every factual line traces to `sources.md`. Opinion lines are marked as opinions in the script (see D6).

---

### Use Case 2: Choosing a level and a focus
**Scenario:** A practitioner preparing for an interview wants depth on system design and no company history.

**Flow:**
1. User: `/podcast interviewing at Acme for staff backend --level expert --focus "data platform, on-call culture"`
2. The brief records the level and focus. Each focus area gets its own research agent, within the `--depth` budget.
3. Focus segments get about 2× their outline share, taken proportionally from the other segments.
4. At `expert`, standard terms aren't defined, and the hosts argue trade-offs. Their stances are about the trade-off,
   not about basics.
5. Afterwards: "go deeper on on-call". A follow-up episode reuses `research/` and `sources.md` and researches only
   the gap.

**Success Criteria:**
- In `chapters.json`, focus segments get ≥ 1.7× their default share.
- The follow-up episode does not re-run research areas that are already on disk.

---

### Use Case 3: An earned reaction and a point of view
```
ALEX: One customer is forty-one percent of their revenue.
MAYA: Forty-one. One customer.
ALEX: One customer.
[pause 1]
MAYA: My read? That changes how I'd hear everything else they told us. If that client leaves, so does the story.
ALEX: I'd push back a little. That client has renewed for six years. It's concentrated, but it isn't fragile.
MAYA: Maybe. I'd still ask about it in the interview.
```
**Success Criteria:** the reaction follows a verified fact, the opinion is marked ("My read?"), and the disagreement
is left open.

---

### Use Case 4: "Faster" / "slower"
The user says "that felt slow". The episode re-renders with the next pacing preset. Only the gaps change, the cache
covers every line, and it takes seconds. The script is untouched.

---

## Architecture Decisions

> **Decided 2026-10-03.** See `phase-human-touch-decisions.md`. D1, D3 and D7 were confirmed as written. **D5 and D8 differ from the leaning:** non-lexical sounds are allowlisted in QA rather than banned, and `relaxed` is the default for every cast, solo included. The ear-test episode, the readout and the eval judge are decided there too.

### D1: Rules before code, proved by ear (Decided)
- **Design:** Milestone 1.2 rescripts one segment of an existing episode under the new rules, renders the old and new versions
  with the **current** renderer, and the owner A/Bs them. Renderer work starts only after that.
- **Rationale:** the baselines (0 pauses, 2–4% short lines) show the gap is in the writing. If the rules alone don't
  win by ear, no gap table will save them.

### D2: Teller and listener roles, swapped per segment (Adopted, not separately asked)
- **Design:** replace two-host's fixed "Maya asks, Alex answers, Maya reframes" with roles per segment. The listener
  host asks the audience's question, reacts in 1–5 words, and recaps. Panel: the moderator usually listens, and
  advocate and sceptic take turns telling. Solo: the narrator puts questions to the listener and leaves pauses
  (mechanic 8).
- **Rationale:** "two narrators taking turns" is the diagnosis, and this is the direct fix.

### D3: A stance per host per episode (Decided: agent picks, user can override)
- **Design:** `brief.md` gains `stances:` with one line per speaker, chosen by the agent from what the research
  shows is genuinely contested, announced to the user in one line before scripting, and overridable. Rules: at least one disagreement per episode, and not always resolved. On a `debate`/`panel`, the
  stances are the sides that already exist.
- **Rationale:** a point of view is the feedback item the current plugin can't produce at all, because the casts
  give temperaments but not positions.

### D4: Emotion is written, not synthesised (Adopted, not separately asked)
- **Design:** replace "no wow" with an **earned-reaction** rule: one felt moment per segment (surprise, unease, a
  wrong first guess), always tied to a verified fact and never used to open a segment. Each cast file gets a
  `## Reactions` section with phrasings that render well.
- **Rationale:** Kokoro can't act (verified). Punctuation adds timing but not feeling, so the words have to carry it.

### D5: Reactions are mostly lexical, plus a QA allowlist for a few sounds (Decided; differs from the leaning to ban them)
- **Design:** reactions are mostly words ("Huh.", "Wait.", "Okay.", "Honestly?", repeat-backs). `qa.py` gains an
  allowlist (`hmm`, `mm-hm`, `uh-huh`, `huh`, `ha`, plus their common mishearings) treated as optional: not required
  for coverage, and not counted as EXTRA AUDIO. Writing rule: ≤ 1 such sound per segment, never a line on its own.
  pacecheck counts them. Every other QA check keeps its strictness.
- **Rationale:** the owner wants that texture. The probe showed these sounds fail QA today, so the allowlist is what
  makes them usable. The ear test checks whether Kokoro renders them acceptably.

### D6: Opinions are marked, facts are traced (Adopted, not separately asked)
- **Design:** opinions use spoken markers ("My read…", "I think…", "Honestly…"). Facts keep tracing to `sources.md`.
  The judged eval checks that no opinion is phrased as fact, and no fact is softened into an opinion to dodge
  verification.
- **Rationale:** keeps the "verification is the product" non-negotiable intact while allowing a point of view.

### D7: Depth is two axes (Decided)
- **Design:** `--depth` stays as research effort. Add `--level intro|informed|expert` (with `default_level` in
  `userConfig`) and `--focus "<a>, <b>"`, capped at 3 aspects. Alternative: overload `--depth`.
- **Rationale:** "deep research at intro level" and "quick research pitched at experts" are both real requests.

### D8: Pacing presets and a context-aware gap table (Decided: `relaxed` default for every cast)
- **Design:** `--pacing brisk|relaxed|spacious`, with `default_pacing=relaxed` in `userConfig` for all casts, solo
  included. `brisk` reproduces the 0.2.0 gaps byte for byte. The gap depends on
  the previous line: longer after a question, a short reaction or a dense line, and shorter in quick back-and-forth.
  `estimate_seconds()` uses the same table, and `WPM` and the SKILL.md budget are re-measured afterwards.
- **Rationale:** the fixed 0.32 s is literally the "constant pace". Gaps aren't cached, so tuning them is free.

---

## Script Rules Architecture

> **Superseded during execution (owner ear tests; see the decisions doc):**
> - Row 1, "swap roles between segments" → **fixed roles**: on two-host, Maya teaches and Alex learns all episode (E19).
> - Row 7, "15–30% of lines ≤ 6 words" → **about half the sentences ≤ 6 words**, pacecheck band 40–70% (E16).
> - Row 5, "`[pause 2]` after a question to the listener" → the **measured pause ladder**: 1.2 s landing, 1.5 s after
>   a quote, 2 s at a wrap, 2.5 s before opinions, and no long silence after a question (E7, E8, E10).
> - Added: "Teach, don't present" (E9/E10), inline thinking beats and `...` holds (E11), and the line-by-line
>   self-check against `sources.md` (E18).

These additions go to `SKILL.md` §4, and existing rules are kept: honesty, "quote", spellings, the word budget and
`sources.md` tracing.

| Rule | From mechanic | Checked by |
|---|---|---|
| Teller and listener roles per segment, swapped between segments | 10 | pacecheck (role heuristic) + judged |
| Arc: stakes → setup → slow down → short line for the turn → `[pause 1–1.5]` → reaction → coda | 2, 3, 4 | judged |
| One felt moment per segment, tied to a verified fact | 1, 9 | judged |
| A stance per host in `brief.md`; ≥ 1 disagreement, not always resolved | 7 | judged |
| `[pause 1]` after a surprising number or quote; `[pause 2]` after a question to the listener; ≥ 1 per 90 s | 8 | pacecheck |
| One-line recap ("So, sit with that: …") before a new idea | 6 | judged |
| Vary line length: 15–30% of lines ≤ 6 words | 3, 4 | pacecheck |
| Repeat the line to remember, once, near the end of the segment | 6 | judged |
| ≥ 1 concrete, picture-able image per segment | 5 | judged |
| Mostly lexical reactions; ≤ 1 allowlisted sound per segment, never alone on a line; no performed enthusiasm; no reaction as a segment opener | D4, D5 | pacecheck (sound count) + judged |

Angles get a `## Level notes` section. Casts get `## Reactions`, and `## Stance` guidance on what positions suit the
persona.

## Pacing Architecture

`pacecheck` runs as part of `render.py --dry-run`. It is deterministic and offline, and is the eval suite's
deterministic layer. In v1 its findings are warnings (exit 0); `--strict` turns them into exit 4. `--selftest`
covers every metric.

```python
GAPS = {  # seconds at pacing=relaxed. brisk = every value 0.32 and segment 1.1, as in 0.2.0
    'continue': 0.25,   # same speaker, next line
    'handoff':  0.45,   # speaker change
    'reaction': 0.60,   # previous line was <= 5 words
    'question': 0.70,   # previous line ends with '?'
    'dense':    0.80,   # previous line held >= 2 figures
    'segment':  1.60,   # '---'
}
```

## Depth Architecture

| Level | Assumes | Explains | Hosts' stances are about |
|---|---|---|---|
| intro | nothing | every term, one image per concept, a recap per segment | whether it matters to you |
| informed (default) | the basics | new or contested terms | what it means |
| expert | the field | nothing standard | trade-offs and edge cases |

---

## UI Structure

There is no visual UI. This is the CLI/skill surface:

```
/podcast <topic> [--level intro|informed|expert] [--focus "<a>, <b>"] [--pacing brisk|relaxed|spacious]
                 [--depth quick|standard|deep] ...existing flags
"go deeper on <aspect>"   → follow-up episode reusing research/
"slower" / "faster"       → re-render with the next pacing preset (gaps only)
```

---

## Technical Considerations

### Performance & Scalability
- A pacing-only re-render is assembly only. Every line is a cache hit.
- New reaction and recap lines are synthesised once each.
- `--focus` adds at most 3 research agents, inside the `--depth` budget.

### Error Handling
- Unknown `--level` or `--pacing`: exit 2, naming the valid set.
- `--focus` that matches no research area: create one and record it in the brief.
- pacecheck warnings in a non-interactive run: render anyway and append the warnings to the `brief.md` outcome.

### Data Flow
`brief.md` (level, focus, pacing, **stances**) → research (focus areas) → verify (unchanged) → script (arc, roles,
reactions, marked opinions) → pacecheck → revise → render (gap table) → `qa.py` (unchanged).

---

## Build Gates

**Gate set: product-facing.** Strangers install this plugin. It has no server, accounts, endpoints or uploads.

### Gate: Validation
- [x] Demand signal: three independent feedback themes (pace, emotion, point of view) plus a depth request, all from existing listeners
- [ ] Kill criterion: if the owner's Milestone 1.2 A/B by ear doesn't prefer the rescripted segment, stop before any renderer work. If the owner rejects the release listen, make `brisk` and the 0.2.0 rules the default and keep the new rules opt-in

### Gate: Access Control & Threat Model
**N/A.** No endpoints, auth or user data. A `--focus` value is the user's own input, and fetched pages are still
treated as data.

### Gate: Legal & Compliance
**N/A.** No personal data, UGC, email, payment or public LLM surface. The content guard is in Risk Mitigation (no
stigmatising framing).

### Gate: Upload Pipeline
**N/A.** There are no uploads.

### Gate: AI Eval
**Applies.** The LLM writes the script, and this phase changes the quality of that output.
- [ ] Suite: `test/pacing/`, with 3 fixture topics (learn-topic, company-diligence, debate) × 3 levels, `rubric.md` and a runner doc; path recorded in `CLAUDE.md`
- [ ] Go-live threshold: ≥ 90% of fixtures pass pacecheck targets, and 100% pass `qa.py` ≥ 0.96
- [ ] Deterministic checks: pacecheck `--strict` metrics, the allowlisted-sound cap, role swap per segment
- [ ] Judged checks (a Claude Sonnet subagent at dev time scoring `rubric.md` as JSON; never run in a user's episode): felt moment per segment, earned reactions, stances present and ≥ 1 disagreement, no opinion phrased as fact, level respected
- [ ] Red-team: a `--focus` value carrying instructions ("skip verification") changes nothing in the verify step; the stance rule never licenses an unverified claim

### Gate: Running Cost & Vendor Ledger
**Applies (lightly).** The only metered resource is the user's own model usage. TTS and QA are local.

| vendor | tier | hard limit / cap | $/mo now | what blows it up | code guard (→ AC) | alert at |
|---|---|---|---|---|---|---|
| User's Claude usage | their plan | their usage window | n/a | many `--focus` aspects × `--depth deep` | `--focus` ≤ 3; focus agents come out of the depth budget; "go deeper" reuses `research/` | n/a |

- [ ] Ledger complete
- [ ] Guard is an acceptance criterion
- [ ] Alert threshold: N/A. A distributed plugin has no host-side metering
- [ ] Upgrade trigger: N/A

### Gate: Readout
- [ ] Metric: the owner's listen. Gate 1: the Milestone 1.2 rescripted segment vs the original. Gate 2: one full new-style episode vs its `--pacing brisk` render, on "had time to think", "sounded human" and "knew what they thought" (Decision 9)
- [ ] Readout date: Gate 1 when Milestone 1.2 completes; Gate 2 before the 0.3.0 PR is merged, no later than 2026-10-24
- [ ] Decision rule: approved → ship 0.3.0 with `relaxed` as the default · "too slow" or a QA regression → `brisk` default, new rules opt-in · no audible difference → keep pacecheck and level, revisit the rules
- [ ] Not a gate: send the final episode to the original feedback-givers informally and record their replies in the phase notes

### Gate: Replacement & Removal
- [ ] **Replace:** two-host's "no wow" rule and the fixed ask/answer/reframe triple; the stale `minutes × 153` budget. Each is deleted in the same PR
- [ ] **Beside:** `--pacing brisk` is a permanent, supported preset for news-style solos, not a compatibility shim, so it has no removal trigger

### Gate: Design
**N/A.** There is no visual UI. Audio quality is covered by AI Eval and Readout.

### Gate: Documentation (the 6 docs)
- [x] PRD  [ ] TRD (decisions doc)  [ ] App Flow (N/A; covered by the UX flows)  [ ] UI/UX Brief (N/A)  [ ] Backend Schema (N/A; only new `brief.md` fields)  [ ] Implementation Plan

---

## Acceptance Criteria

### Functional
- [ ] Milestone 1.2: one rescripted segment and the original, both rendered with the current renderer; QA passes; every fact traces to `sources.md`; the owner prefers the new version by ear
- [ ] `SKILL.md` §4 carries every rule in the Script Rules table, and no existing rule is removed
- [ ] Every cast has `## Reactions` and stance guidance; two-host's roles are per segment
- [ ] `brief.md` template includes `stances:`, `level:`, `focus:` and `pacing:`
- [ ] `render.py --dry-run` prints pacecheck (short-line share, avg/stdev, pause rate, longest pause-free stretch, longest run, role swap, allowlisted-sound count); `--selftest` covers each metric; `--strict` exits 4
- [ ] `qa.py` allowlist: allowlisted sounds and their mishearings are optional (not required, not EXTRA AUDIO); every other check is unchanged; `--selftest` proves a dropped lexical line still fails
- [ ] Stances are announced in one line before scripting and recorded in `brief.md`; a user override replaces them
- [ ] `default_level` and `default_pacing` are in `userConfig`; `default_pacing=relaxed` applies to every cast
- [ ] `--pacing brisk` audio is identical to 0.2.0 (decoded PCM; MP3 bytes carry a date tag); changing pacing re-synthesises 0 lines
- [ ] Dry-run vs rendered length within 5% on 3 fixtures; `WPM` re-measured, and SKILL.md's budget matches `render.py`
- [ ] `--level` and `--focus` are accepted, recorded and change the script (judged); a 4th focus aspect is rejected
- [ ] "go deeper on X" reuses `research/` and verifies only new claims
- [ ] Every `--selftest` passes; `claude plugin validate --strict` passes for the plugin and the repo; `test/stranger.sh` passes
- [ ] `version` is 0.3.0 in both `plugin.json` and `marketplace.json`
- [ ] The privacy grep is clean on every new file, this docs folder included
- [ ] Nothing is pushed to the public repo without the owner's explicit go-ahead

### User Experience
- [ ] Fixtures: 15–30% of lines ≤ 6 words, ≥ 1 pause per 90 s, ≥ 1 felt moment per segment, ≥ 1 disagreement per episode
- [ ] 0 opinions phrased as fact, and 0 reactions that don't follow a verified line
- [ ] The owner approves both Readout gates

### Performance
- A pacing-only re-render of a 20-minute episode takes < 30 s
- QA coverage is ≥ 0.96 on every fixture

---

## Implementation Phases

See `docs/phases/phase-human-touch/phase-human-touch-implementation-plan.md` (written after `decide`).

1. **Prove by ear (rules only):** draft the script rules, rescript one segment of an existing episode, render both,
   and run the owner A/B. This decides whether everything else proceeds.
2. **Measure:** add pacecheck to `--dry-run` and take baselines from the 0.2.0 fixtures. Every metric target depends
   on it.
3. **Pacing:** the gap table, `--pacing`, estimate parity, and re-measuring `WPM` and the SKILL.md budget.
4. **Point of view and emotion:** cast `## Reactions` and stance guidance, `brief.md` stances with a one-line
   announcement, SKILL.md rules, and the `qa.py` allowlist for non-lexical sounds.
5. **Level and focus:** the flags, angle `## Level notes`, focus research areas, and the "go deeper" follow-up.
6. **Eval and release:** the fixture suite, the subagent-judged rubric, the owner's release listen, and 0.3.0 behind the owner's go-ahead.

---

## Out of Scope (v1)

### Not Building
- An emotive TTS engine. It would break the small-install and Tier 0 promises.
- Breaths, music beds, sound effects, or laughter as audio (a written "ha" through the allowlist is in scope).
- Overlapping speech (true interruptions), since the renderer is sequential.
- Per-word emphasis markup.

### Future Considerations
- An optional `upgrade voice-expressive` tier, if writing plus timing plateaus.
- Default level and preferred host stances in the listener profile.
- A blind A/B with several listeners, if the owner's ear proves too narrow a test.

---

## Dependencies

### External
- **Kokoro v1.0** (already pinned): punctuation-driven timing.
- **whisper (qa-base+)**: verified to transcribe lexical reactions.

### Internal
- `SKILL.md` §Invocation and §4; every `casts/*.md`; every `angles/*.md`; `render.py` (parser,
  `estimate_seconds()`, dry-run); `plugin.json` `userConfig`; `test/stranger.sh`.

### Libraries to Add
None. Standard library only.

---

## Risk Mitigation

### Risk: Emotion becomes performance (the NotebookLM failure)
**Mitigation:**
- Every reaction must follow a verified line, and none may open a segment.
- The judged eval flags unearned reactions, and the cap of one allowlisted sound per segment keeps the cheapest tells rare.

### Risk: A point of view erodes trust in the facts
**Mitigation:**
- Opinions carry spoken markers, facts trace to `sources.md`, and the judged eval checks both directions.
- On `company-diligence`, stances stay analytical ("concentrated, not fragile"), never cheerleading.

### Risk: Storytelling rules import the source clip's framing
**Mitigation:**
- A cast-level rule: no demeaning comparisons, and no stigmatising language about health or identity. Humour and
  vulnerability come from the host, never at someone's expense.

### Risk: Breathing room squeezes out verified content at a fixed `--minutes`
**Mitigation:**
- The angle's must-verify claims are protected. `expert` cuts explanation, not facts.

### Risk: "Relaxed" reads as sluggish
**Mitigation:**
- "faster" is a seconds-long re-render, and `brisk` is permanent.

---

## Open Questions

> **Most were resolved in `decide` on 2026-10-03.** See `phase-human-touch-decisions.md`. Three outcomes differ from
> this PRD's original leanings: non-lexical sounds are allowlisted, not banned (D5); `relaxed` is the default for
> every cast, solo included (D8); and the readout is the owner's ear, not a blind panel (Decision 9).

### Technical
- What are the exact gap values? Tune them from the 1.2 and 3.1 listening, not by guesswork. (This belongs to the plan.)
- Is the role-swap heuristic (who asks more `?` lines in a segment) reliable enough to warn on? (Calibrate on the fixtures.)

### Product
- None open.

### Process
- None open.

### Resolved
| Question | Answer | Decided By | Date |
|----------|--------|------------|------|
| Switch voice engines to get emotion? | No. Writing and timing first | PRD | 2026-10-03 |
| Can lexical reactions pass QA? | Yes, coverage 1.00 on the probe; non-lexical sounds fail today | Probe | 2026-10-03 |
| Pilot order | Private twin first, judged by ear, then this public port | Owner's plan | 2026-10-03 |
| Prove by ear before code? | Yes: rules-only ear test first | Owner (Decision 1) | 2026-10-03 |
| Which episode for the ear test? | Learning to sail, segment 3 | Owner (Decision 2) | 2026-10-03 |
| Who picks stances? | The agent, announced in one line; the user can override | Owner (Decision 3) | 2026-10-03 |
| One depth knob or two? | Two: `--level` + `--focus`; `--depth` stays research effort | Owner (Decision 4) | 2026-10-03 |
| Non-lexical sounds? | QA allowlist (**differs from the leaning to ban them**) | Owner (Decision 5) | 2026-10-03 |
| Relaxed default for solo too? | Yes, for every cast (**differs from the leaning**) | Owner (Decision 6) | 2026-10-03 |
| Should pacecheck block renders? | No: warn, agent must revise; `--strict` → exit 4 | Owner (Decision 7) | 2026-10-03 |
| Eval judge | Claude Sonnet subagent at dev time, `test/pacing/rubric.md` | Owner (Decision 8) | 2026-10-03 |
| Readout | The owner's ear; blind panel dropped (**differs from the leaning**) | Owner (Decision 9) | 2026-10-03 |

---

## Next Steps

1. **Finalize requirements:** this document.
2. **Interactive decisions:** done. See `phase-human-touch-decisions.md`.
3. **Create the implementation plan:** run `/pm-agent plan human-touch`.
4. **CLAUDE.md update:** record the eval suite path (`test/pacing/`) once it exists, and note that `PLAN.md` is referenced but absent.

---

**Status:** Requirements complete and ready for decisions
