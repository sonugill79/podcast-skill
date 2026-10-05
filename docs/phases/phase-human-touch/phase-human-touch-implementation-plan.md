# Phase Human Touch: Implementation Plan & Task Breakdown

**Created:** 2026-10-03
**Last Updated:** 2026-10-03
**Status:** Complete (push pending owner go-ahead)
**Dependencies:** none from earlier phases. The milestones form one serial chain, and Milestone 1.2 is a hard owner gate:
nothing after it starts until the owner prefers the rescripted segment by ear.

---

## Progress Overview

_This table is the SINGLE source of truth for progress. Current milestone = the first non-Complete row. Do not duplicate per-milestone status anywhere else in this document._

| Milestone | Status | Size | Started | Completed | Notes |
|-----------|--------|------|---------|-----------|-------|
| **Phase 1: Prove by ear** |
| 1.1 Script rules + two-host cast | Complete | S | 2026-10-03 | 2026-10-03 | opus build + opus review (FAIL 2×MEDIUM → fixed: E3, E4). Decisions E1–E5 |
| 1.2 Ear test (owner gate) | Complete | S | 2026-10-03 | 2026-10-04 | **Owner: v5 "much better"** (A → v2 no clear win → v3/v4 better → v5 much better). Lesson shape + pause ladder written into §4/two-host (E10). Remaining owner notes (robotic, short thinking beats, flat emotion) → L17 |
| **Inserted 2026-10-04 by owner direction (E11/E12)** |
| 3.1a Inline beat (pulled forward from 3.1) | Complete | S | 2026-10-04 | 2026-10-04 | Inline `[pause N]` (render/qa/config, `plan_assembly` planner, `line_segments`). Opus review FAIL (untested assembly) → fixed; selftests render 205/qa 135; v5 PCM identical to main; v6 sent. Holds = `...` rule (no code) |
| X1 Expressive-engine bake-off | Complete | M | 2026-10-04 | 2026-10-04 | Owner pick: Qwen3-TTS + voice conversion (E13/E14). Qwen → next phase "Expressive Voice"; VC → private experiment. Scratch installs deleted |
| **Phase 2: Measure** |
| 2.1 pacecheck in `--dry-run` | Complete | M | 2026-10-04 | 2026-10-04 | 7 warning kinds (adds BANNED_SOUND), per-segment NO_PAUSE/FLAT_LINES, `--strict` exit 4. Opus review FAIL (2 MEDIUM) → fixed with reds. Original seg 3 exit 4; v5/v6 clean (E16) |
| 2.2 Baselines | Complete | XS | 2026-10-04 | 2026-10-04 | Only one TBD cell existed (longest run): 51/60/61 words; numbers only. Short-sentence target superseded by E16 (PRD text updated in 6.2) |
| **Phase 3: Pacing** |
| 3.1 Gap table + `--pacing` | Complete | M | 2026-10-04 | 2026-10-04 | GAPS (+`sentence`), renderer sentence split, `Episode` helper, `default_pacing=relaxed`. relaxed(v6.turns) PCM == approved v6; brisk PCM == main ×3. Opus review FAIL (3 MEDIUM) → fixed, 41 mutants red (E17) |
| 3.2 Re-measure WPM + budget | Complete | S | 2026-10-04 | 2026-10-04 | WPM 163 + −0.35 s/chunk (fit on 14 renders); relaxed estimate within 3.7% on 4 scripts; SKILL.md budget 150 wpm (relaxed). Orchestrator review (diff read; pacecheck verdicts unchanged) |
| **Phase 4: Emotion & point of view** |
| 4.1 `qa.py` non-lexical allowlist | Complete | M | 2026-10-04 | 2026-10-04 | Alignment-scoped optional sounds; names never sounds; replace-block budget keeps every lexical word paired. Opus review FAIL (Tim→him slipped NAMES) → fixed; reviewer probes re-run by orchestrator: all attacks still fail. huh +"hi" (L19) |
| 4.2 Panel/solo casts + stance flow | Complete | S | 2026-10-04 | 2026-10-04 | Roles/Reactions/Stance for panel + solo; §3 stance announce/override (Verified-only, pushback); `--pacing` usage. Opus review FAIL (3 MEDIUM) → fixed; SAME_TELLER scoped to two voices (orchestrator, red shown); `--pacing` + revise-on-⚠ in §4/§5 commands |
| **Phase 5: Depth** |
| 5.1 `--level`, `--focus`, go-deeper | Complete | M | 2026-10-04 | 2026-10-04 | `default_level` (config/env/userConfig + parity selftest), Level notes ×5, focus slot formula + cleaning (red-team), go-deeper (personal-source exclusion, staleness). Opus review FAIL (2 MEDIUM) → fixed. Judged level AC moves to 6.1 |
| **Phase 6: Eval & release** |
| 6.1 Eval suite `test/pacing/` | Complete | M | 2026-10-04 | 2026-10-05 | 10 fictional fixtures (3 angles × 3 levels + red-team), rubric, runner, check_sources, CI step. Deterministic 10/10; QA 10/10 ≥ 0.96. Judged (3 Sonnet judges, per-row majority): 9/10 → after L35 fixes **10/10 fixtures clean**, after 5 judge rounds and a new §4 self-check rule (E18). SAME_TELLER FP 0% → kept |
| 6.2 Release 0.3.0 (owner gate) | Complete | S | 2026-10-05 | 2026-10-05 | **Owner approved** (2026-10-05): fixed roles + relaxed (E19), Qwen direction for next phase (E21), 0.2.1 patch, noise accepted, PLAN.md dropped. stranger.sh ALL PASS; hostile matrix 9/9; ledger 0 open; retro + action items written. Push awaits owner go-ahead (A3) |

**Status Key:** Not Started | In Progress | Complete | Blocked — a Blocked row must carry the ask in the Notes column in the form "I need {X} from {owner} to move {milestone} by {date}". "Blocked" with no named ask is not a status, it is a hidden Not Started.
**Size Key:** XS/S/M complexity buckets — no day/week estimates (no velocity basis exists for AI-executed work).

---

## Phase Gates (tier: Lightweight)

**Why Lightweight:** one implementing agent, a strictly serial Execution Graph (every wave holds exactly one
milestone, so override 2b-f doesn't apply), and no task prompts are generated for parallel agents. The owner's two
listening gates are waits, not build sessions. **Upgrade to Full** the moment any wave is parallelised.

- [ ] Gate 0 — tier chosen; the plan sections below exist; repo addendum `docs/ops/phase-gates-addendum.md` found or created
- [ ] Gate 1 — every task prompt & plan AC carries the cross-cutting rules + Universal Clauses verbatim
- [ ] Gate 1 — every seam/join has a named owner (Full) — N/A Lightweight; seams are still listed under Cross-Cutting Rules
- [ ] Gate 1 — every from-scratch general-purpose component names the alternative it rejected (Step 2.6)
- [ ] Gate 1 — inherited rules re-derived; precedence chains have per-action eviction rules
- [ ] Gate 2 — seam sweep after every parallel wave (Full) — N/A, serial
- [ ] Gate 3 — deviations ledger has zero `open` rows before the owner's release listen
- [ ] Gate 3 — every non-trivial execution-time choice is in the decisions doc under "Execution decisions"
- [ ] Gate 3 — hostile-env matrix: one pass per row, all green or ledgered
- [ ] Gate 3 — every changed UI surface SCREENSHOTTED and read — N/A (no UI); the audio equivalent is the owner's listen
- [ ] Gate 3 — every ticked AC carries its EVIDENCE output; no tick reads `pending`
- [ ] Gate 3 — perf-smell sweep over each milestone's diff; every hit resolved or recorded
- [ ] Gate 4 — any ramp/flip PR includes its variant-pinning test change (the `relaxed` default flip ships with the brisk byte-identity test, same PR)
- [ ] Gate 4 — readout recorded (metric + date + decision rule) in the merge PR
- [ ] Gate 5 — retro written AND action-items created in the same sitting; agnostic lessons upstreamed to the skill

---

**Session Resume:** Use `/pm-agent gen-prompt human-touch` to generate a resume prompt for AI agents.

---

## Active Blockers & Issues

**No active blockers** - Ready to start

<!-- Add blockers here as they come up:
- [ ] Issue description
  - Impact: High/Medium/Low
  - Blocker for: Milestone X.X
  - Status: Investigating / Waiting / Resolved
  - Notes: ...
-->

---

## Overview

This document is the implementation plan for Phase Human Touch, based on
`docs/phases/phase-human-touch/phase-human-touch-requirements.md`.

**Scope:**
- Script rules that turn two narrators into a teller and a listener: an arc per segment, earned reactions, a stance per host, pauses and varied line length.
- Measurement (pacecheck) and pacing (context-aware gaps, `--pacing`, `relaxed` default everywhere).
- Allowlisting non-lexical sounds in QA; `--level`/`--focus` depth; a dev-time eval suite; release 0.3.0.

**Related Documents:**
- **Requirements:** `docs/phases/phase-human-touch/phase-human-touch-requirements.md`
- **Decisions:** `docs/phases/phase-human-touch/phase-human-touch-decisions.md`
- **Project Context:** `CLAUDE.md` (non-negotiables: nothing personal ships, Tier 0 always works, no sudo, verification is the product, bump `version` on every user-visible change)

---

## Architecture Overview

```
 user ──/podcast flags──▶ SKILL.md (the model's instructions)
                          │  brief.md: level · focus · pacing · stances
                          ▼
     research (focus areas) ──▶ verify (unchanged) ──▶ script.txt
                                                        │  rules: arc, roles, reactions, pauses
                                                        ▼
                     render.py --dry-run ──▶ pacecheck report ──(revise)──┐
                                                        │◀────────────────┘
                                                        ▼
       render.py --pacing P ──▶ events ──▶ gap_for(prev, next, P) ──▶ assemble ──▶ MP3
                                   ▲ TTS cache (unchanged key: gaps never re-synthesise)
                                                        ▼
                     qa.py ── NONLEXICAL (optional tokens) ──▶ pass / fail (gates unchanged)

 config.py: DEFAULTS{default_pacing, default_level} · ENUM_CHOICES · NONLEXICAL (shared by render.py + qa.py)
```

### Key Interfaces / Contracts

| Interface | From | To | Description |
|-----------|------|----|-------------|
| `brief.md` fields `level:`, `focus:`, `pacing:`, `stances:` | SKILL.md (model) | script stage, eval rubric | One line each; `stances:` holds one `SPEAKER: position` per host |
| `pacecheck` stdout block + `--strict` exit 4 | `render.py --dry-run` | the model, CI, eval runner | Fixed line prefixes (below), so the model and CI can parse them |
| `--pacing brisk\|relaxed\|spacious` | user / SKILL.md | `render.py` | Default from `config.default_pacing`; `brisk` = 0.2.0 gaps exactly |
| `GAPS[pacing][kind]` + `gap_for()` | `render.py` | assembly + `estimate_seconds()` | One table drives both, so estimate and render agree |
| `config.NONLEXICAL` | `config.py` | `render.py` pacecheck, `qa.py` | Allowlisted sounds plus their mishearings; one source of truth |
| `default_pacing`, `default_level` | `plugin.json` userConfig | `config.py` DEFAULTS/ENUM_CHOICES/ENV_OVERRIDES | Same shape as `default_cast` |
| Cast `## Reactions`, `## Stance` | `casts/*.md` | the model writing the script | Prose instructions, not machine-read |
| Angle `## Level notes` | `angles/*.md` | the model | What each level changes for that angle |

---

## Implementation Phases

### Phase 1: Prove by ear

**Goal:** Find out whether the script rules alone make an episode sound human, before writing any code.
**Rollback:** revert the SKILL.md/cast commit. No code ships in this phase.

---

#### Milestone 1.1: Script rules + two-host cast (S)

**Objective:** Write the new script rules into `SKILL.md` §4 and the two-host cast, keeping every existing rule.
**Owns:** `plugins/podcast/skills/podcast/SKILL.md` (§1 Brief and §4 Script only), `plugins/podcast/skills/podcast/casts/two-host.md`
**Tier:** opus — prose that shapes model behaviour, and a new pattern for the repo (`grep -n "stance\|Reactions" casts/*.md SKILL.md` → 0 hits) · **Review:** opus

**Tasks:**
1. `SKILL.md` §1: add `level`, `focus`, `pacing`, `stances` to the `brief.md` field list.
2. `SKILL.md` §4: add the Script Rules table from the PRD as instructions (arc, roles, felt moment, stance, pauses,
   short lines, repeat line, concrete image, reactions). Add the opinion-marker rule. Add the non-lexical cap (≤ 1
   per segment, never alone on a line).
3. `casts/two-host.md`: replace "Maya asks, Alex answers, Maya reframes" with teller/listener roles that swap per
   segment; replace "No wow…" with the earned-reaction rule; add `## Reactions` (phrasings) and `## Stance` (what
   positions suit each persona). Keep the Opening section and the voices block byte-identical.
4. Leave the budget line (`minutes × 153`) for 3.2. Note it in the ledger as a known stale value.

**Code Template:**

```markdown
<!-- plugins/podcast/skills/podcast/SKILL.md §4 — appended rules   [Contract] (rule names are referenced by the rubric in 6.1) -->
### Make it sound like people (teller and listener)
- **Roles.** In each segment one host tells and one listens; swap between segments. The listener asks the audience's
  question, reacts in 1–5 words ("Wait. In September?"), and recaps.
- **Arc per segment:** stakes → setup or character → slow down in short lines → the turn in one short line →
  `[pause 1–1.5]` → a reaction → a coda or callback.
- **One felt moment per segment** — surprise, unease, a wrong first guess — always right after a verified line,
  never as a segment's first line.
- **A point of view.** Use the `stances:` in brief.md. Hosts say what a fact means to them, marked as opinion ("My
  read…", "I think…", "Honestly…"). At least one disagreement per episode; leave one unresolved now and then.
  Opinions never carry a fact that isn't in sources.md.
- **Room to think.** `[pause 1]` after a surprising number or quote; `[pause 2]` after a question put to the
  listener; a one-line recap before a new idea; at least one pause per ~90 s.
- **Vary line length.** 15–30% of lines at six words or fewer.
- **Repeat the one line to remember**, once, near the segment's end. **One concrete image** per segment.
- **Sounds.** Prefer words ("Huh.", "Okay.", "Wait."). At most one "hmm"/"mm-hm"/"uh-huh"/"ha" per segment, and
  never as a whole line.
- **Never** punch down: no demeaning comparisons, no stigmatising language about health or identity.
```

```markdown
<!-- brief.md excerpt   [Contract] -->
level: informed
focus: data platform; on-call culture
pacing: relaxed
stances:
  MAYA: sceptical that the concentration risk is priced in
  ALEX: thinks six years of renewals make it sticky, not fragile
```

**Acceptance Criteria:**
- [x] Every PRD Script Rules row appears in §4. CHECK: a reviewer ticks the rows one by one. EXPECT: 10/10. EVIDENCE: opus reviewer ticked 10/10 (PRD requirements.md:319-328 → SKILL.md §4 "Make it sound like people" bullets)
- [x] No existing §4 rule removed. CHECK: `git diff -U0 main -- SKILL.md | grep '^-[^-]'` lists only replaced cast-rhythm lines. EXPECT: no honesty/quote/spelling/budget/sources lines removed. EVIDENCE: `grep -c` → 0 (no SKILL.md line removed)
- [x] `two-host.md` voices block and Opening unchanged. CHECK: `python3 scripts/render.py --selftest` + `git diff main -- casts/two-host.md`. EXPECT: selftest OK, no change inside the ```cast block. EVIDENCE: render.py --selftest exit 0; `diff` of Voices..Opening vs main → identical
- [x] Privacy grep clean (CI pattern). EVIDENCE: "no personal data outside attribution"
- [x] Universal Clauses + Cross-Cutting Rules (below) satisfied. EVIDENCE: prose only; deviations ledgered L5–L8; decisions E1–E5; `plugin validate --strict` ×2 passed

**Testing Strategy:**
- **Unit Tests:** `render.py --selftest` (the cast still parses).
- **Integration Tests:** none (prose).
- **Manual Verification:** read §4 top to bottom as the model would, checking that no rule contradicts another (e.g. "short lines" against "one idea per line" — keep both).
- **Declared Verifiers:** CI `validate.yml` (selftests, manifests, privacy grep).

---

#### Milestone 1.2: Ear test — owner gate (S)

**Objective:** Rescript segment 3 of the private twin's "learning to sail" episode under the new rules. Render it
beside the original with today's renderer. The owner picks the better one.
**Owns:** the private twin's episode folder only: `script.humanized.txt`, `*.humanized.mp3`, `*.original-seg3.mp3`.
Nothing in this repo except the Progress row and the ledger, which the orchestrator writes.
**Tier:** opus — creative rewrite under fact-tracing constraints · **Review:** opus (the reviewer checks that every factual line traces to `sources.md`)

**Tasks:**
1. Extract segment 3 of the original script to `seg3.original.txt` (header and lines, unchanged).
2. Write `script.humanized.txt` (segment 3 only) under the 1.1 rules, using only facts already in `sources.md`.
   Include 2–3 non-lexical sounds so Kokoro's rendering of them can be heard.
3. Render both with the same cast, voices pinned (`--no-rotate`) and the current `render.py`. Run `qa.py` on both.
   Non-lexical lines are **expected** to flag before 4.1. List them, and require that everything else passes.
4. Send both files to the owner (local path or their private delivery). Record the verdict in this row's Notes.

**Code Template:**

```bash
# [Sketch] — run inside the private twin's episode folder; paths are illustrative
R=<repo>/plugins/podcast/skills/podcast
python3 $R/scripts/render.py seg3.original.txt  seg3.original.mp3  --cast $R/casts/two-host.md --no-rotate
python3 $R/scripts/render.py script.humanized.txt seg3.humanized.mp3 --cast $R/casts/two-host.md --no-rotate
python3 $R/scripts/qa.py script.humanized.txt seg3.humanized.mp3 --json qa.humanized.json
python3 $R/scripts/render.py script.humanized.txt --dry-run   # duration delta vs original
```

**Acceptance Criteria:**
- [x] The original script and audio are untouched. CHECK: `sha256sum script.txt *.mp3` before and after. EXPECT: identical. EVIDENCE: 62-file baseline (every file outside `ear-test/`) diffed empty before, after v1 and after v2
- [x] Every factual line in the rescript maps to a `sources.md` entry (a reviewer table: line → source). EVIDENCE: opus reviewer table, all lines trace (V1/V2 or research/01 items sources.md vouches for, same as the original); 3 quotes byte-identical to script.txt
- [ ] QA: 0 flags outside the listed non-lexical lines. EVIDENCE: UNMET — v2 `qa.py` exit 0, coverage 0.976, 0 non-lexical flags, 5 other flags (attack/stirn/jive/squeeze/they're/of), each round-tripped in isolation as a whisper-base error with correct espeak phonemes (L9)
- [x] **Owner verdict recorded:** prefers humanized → continue · prefers original → STOP, mark Blocked "I need a rules revision decision from the owner". EVIDENCE: owner 2026-10-04, v5 "much better, write it into the rules"
- [x] Owner's note on how the non-lexical sounds sounded, recorded (this feeds 4.1). EVIDENCE: "Mm-hm" spelled as letters (E8, L14); Huh/Uh-huh no complaint

**Testing Strategy:**
- **Unit Tests:** none.
- **Integration Tests:** `qa.py` on the rendered rescript.
- **Manual Verification:** the owner's A/B listen. This is the gate.
- **Declared Verifiers:** `qa.py` exit code (expected non-zero only on the listed lines).

---

### Phase 2: Measure

**Goal:** Turn the rules into numbers the model and CI can read.
**Rollback:** pacecheck only prints in `--dry-run`, so reverting the commit is enough. It never affects a render.

---

#### Milestone 2.1: pacecheck in `--dry-run` (M)

**Objective:** A deterministic, offline pacing report with warnings, `--strict` → exit 4, and selftest coverage.
**Owns:** `plugins/podcast/skills/podcast/scripts/render.py` (new `pacecheck()` + dry-run output + `--strict` flag + selftests), `plugins/podcast/skills/podcast/scripts/config.py` (`NONLEXICAL` constant + selftest only)
**Tier:** opus — new analysis code, and a `[Contract]` consumed by 4.1, 6.1 and the model · **Review:** opus

**Tasks:**
1. `config.py`: add `NONLEXICAL` (the canonical sounds and their mishearings).
2. `render.py`: `pacecheck(events, chapters)` returns per-episode and per-segment metrics (below). Print it after the
   existing dry-run output. Add `--strict` (exit 4 if any warning).
3. Role heuristic: in each segment, the speaker with the most `?` lines plus ≤ 5-word lines is the "listener".
   Warn when the same speaker is the teller in two consecutive segments. Calibrate it in 6.1, and record any
   false-positive rate in the ledger.
4. Selftests: one fixture per metric, plus a demonstrated red for each warning (mutate, see it fail, revert).

**Code Template:**

```python
# render.py   [Contract] — output prefixes and warning kinds; the metric arithmetic is [Sketch]
FIGURE_RE = re.compile(r'\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|million|'
                       r'billion|percent|\d[\d,.]*)\b', re.I)

def pacecheck(events, chapters, nonlexical=config.NONLEXICAL):
    """-> {'lines', 'short_share', 'avg_words', 'sd_words', 'pauses', 'secs_per_pause',
           'longest_run': (speaker, words, event_idx), 'nonlexical': n, 'warnings': [(kind, msg)]}"""
    total, starts = estimate_seconds(events)
    says = [e for e in events if e[0] == 'say']
    words = [len(e[3].split()) for e in says]
    # ... segment split on chapter indices; per segment: pause-free stretch, role, figures/min ...
    # warning kinds (stable ids): NO_PAUSE, LONG_RUN, FLAT_LINES, SAME_TELLER, NONLEXICAL_ALONE, NONLEXICAL_MANY

def print_pacecheck(pc):
    print(f"pacecheck  lines ≤6 words {pc['short_share']:.0%}   avg {pc['avg_words']:.1f} (sd {pc['sd_words']:.1f})")
    print(f"  pauses {pc['pauses']} (1 per {pc['secs_per_pause']:.0f} s)   longest run "
          f"{pc['longest_run'][0]} {pc['longest_run'][1]} words")
    for kind, msg in pc['warnings']:
        print(f"  ⚠ {kind}: {msg}")
```

```python
# config.py   [Contract]
# Non-lexical reactions qa.py treats as optional and pacecheck counts. Keys are what the script says;
# values are what whisper has been seen to hear instead (probe, 2026-10-03: "hmm" -> "him").
NONLEXICAL = {"hmm": ["him", "hm", "mm"], "mm-hm": ["mmhm", "mhm", "mm hm"], "uh-huh": ["uh huh", "uhhuh"],
              "huh": [], "ha": ["ha ha", "hah"]}
```

**Acceptance Criteria:**
- [x] `render.py --selftest` covers every metric and every warning kind, with a demonstrated red per kind. EVIDENCE: render 255 PASS/0 FAIL; red per kind by builder (12 mutants, sha256 revert identical) + orchestrator BANNED_SOUND mutant → 4 FAIL, reverted identical
- [x] `--dry-run` output for an existing script is unchanged above the pacecheck block. CHECK: diff vs `main` output. EVIDENCE: identical for script.txt and seg3.original (builder + reviewer)
- [x] `--dry-run --strict` exits 4 on a fixture with `NO_PAUSE`, and 0 on a clean one. EVIDENCE: selftest PASS both; real: seg3.original exit 4, v6 exit 0
- [x] Exit 3 still means only "not installed"; dry-run never imports an engine. EVIDENCE: selftest import probe (numpy/kokoro/torch… absent; proven non-vacuous by reviewer); --strict w/o --dry-run → 2
- [x] CI selftests pass without third-party packages. EVIDENCE: all six exit 0 under `python3 -S`

**Testing Strategy:**
- **Unit Tests:** fixture scripts inline in `run_selftest()`, as the existing tests do.
- **Integration Tests:** `--dry-run` on the 1.2 rescript and on its original.
- **Manual Verification:** the warnings on the original seg 3 match what the owner heard as "too fast".
- **Declared Verifiers:** CI "Script selftests".

---

#### Milestone 2.2: Baselines (XS)

**Objective:** Fill in the PRD's `TBD-by-2.2` baselines.
**Owns:** `docs/phases/phase-human-touch/phase-human-touch-requirements.md` (the Quantitative Metrics baseline cells only)
**Tier:** sonnet — mechanical, with a deterministic verifier (the pacecheck output) · **Review:** sonnet → opus not required; doc-only

**Tasks:**
1. Run `--dry-run` on the three existing private scripts and on both 1.2 files. Record **numbers only**: no episode
   names or content (the privacy rule).
2. Update the baseline cells, citing "pacecheck, 2026-MM-DD, 3 production scripts".

**Acceptance Criteria:**
- [x] Every `TBD-by-2.2` cell is filled. CHECK: `grep -c TBD-by-2.2` → 0. EVIDENCE: 0
- [x] CI privacy grep clean on `docs/`. EVIDENCE: "no personal data outside attribution"

**Testing Strategy:** Declared Verifiers: the privacy grep. Manual: the numbers match the pasted pacecheck output.

---

### Phase 3: Pacing

**Goal:** Pauses that depend on context, presets, and an honest length estimate.
**Rollback:** `config.py set default_pacing=brisk` restores 0.2.0 gaps with no deploy. Reverting the commit removes the feature.

---

#### Milestone 3.1: Gap table + `--pacing` + `default_pacing` (M)

**Objective:** Replace the fixed `TURN_GAP` with a gap table looked up by the previous line. `brisk` must be
audio-identical (decoded PCM) to 0.2.0.
**Owns:** `scripts/render.py` (gap table, `gap_for`, assembly, `estimate_seconds`, `--pacing`, selftests), `scripts/config.py` (`default_pacing` in DEFAULTS/ENUM_CHOICES/ENV_OVERRIDES + selftests), `plugins/podcast/.claude-plugin/plugin.json` (userConfig `default_pacing` only)
**Tier:** opus — changes every render's output · **Review:** opus

**Tasks:**
1. `GAPS` table and `gap_for(prev_event, next_event, pacing)`. Both places that use `TURN_GAP` today call it: `estimate_seconds()` (`render.py:571`) and assembly (`render.py:1960`).
2. `--pacing`, defaulting to `config.load()['default_pacing']`. An invalid value → exit 2, naming the valid set.
3. `config.py`: `default_pacing: "relaxed"`, `ENUM_CHOICES['default_pacing']`, `PODCAST_DEFAULT_PACING`.
4. `plugin.json` userConfig entry (same shape as `default_cast`).
5. Selftests: brisk produces the 0.2.0 gap sequence for a fixture; a pacing change hits the cache for every line
   (count synth calls with a fake engine); relaxed differs.
6. Record the cache invariant in the ledger: no `CACHE_VERSION` bump, since gaps are not in the key.

**Code Template:**

```python
# render.py   [Contract] — table shape and kinds; the values are [Sketch], tuned by ear in 3.2
GAPS = {
    'brisk':    {'continue': 0.32, 'handoff': 0.32, 'reaction': 0.32, 'question': 0.32, 'dense': 0.32, 'segment': 1.1},
    'relaxed':  {'continue': 0.25, 'handoff': 0.45, 'reaction': 0.60, 'question': 0.70, 'dense': 0.80, 'segment': 1.6},
    'spacious': {'continue': 0.35, 'handoff': 0.65, 'reaction': 0.85, 'question': 1.00, 'dense': 1.10, 'segment': 2.2},
}
PACINGS = tuple(GAPS)

def gap_for(prev, nxt, pacing):
    """Silence after `prev` (a 'say' event) when `nxt` is also a 'say'. Most specific kind wins."""
    g = GAPS[pacing]
    text = prev[3]
    if text.rstrip().endswith('?'):
        return g['question']
    if len(FIGURE_RE.findall(text)) >= 2:
        return g['dense']
    if len(text.split()) <= 5:
        return g['reaction']
    return g['continue'] if nxt[1] == prev[1] else g['handoff']
# '---' keeps emitting ('pause', SEGMENT_GAP) where SEGMENT_GAP = GAPS[pacing]['segment']; [pause N] is untouched.
```

**Acceptance Criteria:**
- [x] `--pacing brisk` audio is identical to `main` for the stranger.sh script (same voices via `--voices`, fixed `--date`). CHECK: md5 of decoded PCM (`ffmpeg -i x.mp3 -f s16le - | md5sum`) on both. The MP3 bytes carry a date tag that defaults to today (`render.py:1980`), so raw `cmp` is not a valid test. EVIDENCE: see Progress row + E17 (PCM md5 439664fe… stranger brisk == main; config exit 2; validate ✔; synth counts 37/0/0)
- [x] Changing pacing re-synthesises 0 lines (relaxed↔spacious, brisk↔brisk; brisk→relaxed re-synthesises sentence chunks once — E17). CHECK: selftest synth-call count. EVIDENCE: see Progress row + E17 (PCM md5 439664fe… stranger brisk == main; config exit 2; validate ✔; synth counts 37/0/0)
- [x] `config.py set default_pacing=fast` → exit 2 naming brisk/relaxed/spacious. EVIDENCE: see Progress row + E17 (PCM md5 439664fe… stranger brisk == main; config exit 2; validate ✔; synth counts 37/0/0)
- [x] `claude plugin validate --strict plugins/podcast` passes. EVIDENCE: see Progress row + E17 (PCM md5 439664fe… stranger brisk == main; config exit 2; validate ✔; synth counts 37/0/0)
- [x] This milestone's PR carries the brisk byte-identity test (Gate 4: variant pinning ships with the flip). EVIDENCE: see Progress row + E17 (PCM md5 439664fe… stranger brisk == main; config exit 2; validate ✔; synth counts 37/0/0)

**Testing Strategy:**
- **Unit Tests:** `gap_for` per kind; the brisk sequence; enum validation.
- **Integration Tests:** render the 1.2 rescript at all three pacings, with QA on each.
- **Manual Verification:** listen to relaxed vs brisk on the rescript. The owner's preference tunes the values (logged as an execution decision).
- **Declared Verifiers:** CI selftests; `claude plugin validate --strict`.

---

#### Milestone 3.2: Re-measure WPM + fix the budget (S)

**Objective:** Make the dry-run estimate and the SKILL.md word budget match a measured relaxed render.
**Owns:** `scripts/render.py` (the `WPM` constant and its comment), `SKILL.md` (§4 budget line only)
**Tier:** sonnet — mechanical, with a deterministic verifier (estimate vs measured) · **Review:** opus (it touches the script the model writes to)

**Tasks:**
1. Render a full-length relaxed script (the eval fixture, or the 1.2 rescript extended). Measure with `ffprobe`.
   Re-derive `WPM` the way the existing comment does.
2. Replace "minutes × 153 words" with a number taken from the measurement (net of the expected relaxed gaps and pauses).

**Acceptance Criteria:**
- [x] Dry-run estimate within 5% of the measured duration on 3 scripts. EVIDENCE: relaxed +3.4% / +4.1% / −3.7% / −0.3% (375–1710 words); brisk worst +5.7% on short-sentence rescripts (outside AC)
- [x] `grep -n "153" SKILL.md` → 0 hits. EVIDENCE: 0

**Testing Strategy:** Declared Verifiers: `--dry-run` vs `ffprobe` numbers pasted. Unit: the existing estimate selftest is updated.

---

### Phase 4: Emotion & point of view

**Goal:** Let reaction sounds through QA without loosening it, and carry roles and stances into every cast.
**Rollback:** remove `NONLEXICAL` from the `qa.py` lookup (one line), or revert the commit. Cast prose reverts independently.

---

#### Milestone 4.1: `qa.py` non-lexical allowlist (M)

**Objective:** Allowlisted sounds (and their mishearings) are optional: not required, not EXTRA AUDIO. Nothing else changes.
**Owns:** `plugins/podcast/skills/podcast/scripts/qa.py`
**Tier:** opus — touches the QA gate, which is what makes "verification is the product" hold · **Review:** opus

**Tasks:**
1. Normalise both sides. Drop allowlisted tokens from the **expected** stream, and drop the canonical sound or any of
   its mishearings from the **heard** stream, only at positions aligned with an expected sound (a mishearing such as
   "him" elsewhere stays a real word).
2. Report them as `NONLEXICAL n/m heard` (informational).
3. Selftests: (a) an allowlisted line plus whisper's "him" passes; (b) a lexical line dropped beside a sound still
   fails DROPPED; (c) a stray "him" with no expected sound still counts; (d) coverage is unchanged on a script with
   no sounds; (e) red demonstrations for (b) and (c).
4. Step 2.6: the existing ignore-pair mechanism was considered and rejected for this. Ignore pairs are exact
   per-word substitutions and can't express "optional". Record that in DEVIATIONS.

**Code Template:**

```python
# qa.py   [Sketch] — the behaviour in the AC is the contract, not this shape
def strip_nonlexical(exp_tokens, heard_tokens, nonlexical=config.NONLEXICAL):
    """Remove expected sound tokens, and the heard tokens difflib aligns to them, before scoring.
    Returns (exp', heard', count_expected, count_heard)."""
```

**Acceptance Criteria:**
- [x] All five selftests pass, with the reds demonstrated. EVIDENCE: qa 166 PASS (also -S); 17 mutants red, sha256 revert OK; keys_shortfirst equivalent
- [x] Re-run QA on the 1.2 rescript: the previously listed non-lexical flags are gone, 0 new flags. EVIDENCE: v1/v3/v6 real transcripts: only v6 L70 huh→hi removed; lexical matches unchanged (530/518/696)
- [x] `qa.py` output on a sound-free script is byte-identical to `main`. EVIDENCE: seg3.original JSON+log sha256 equal (5794deb1…)

**Testing Strategy:** Unit as above. Integration: real whisper on the 1.2 render. Declared: CI selftests.

---

#### Milestone 4.2: Panel/solo casts + the stance flow (S)

**Objective:** Every cast gets roles, reactions and stance guidance. SKILL.md gets the stance announcement and override.
**Owns:** `casts/panel.md`, `casts/solo.md`, `casts/README.md`, `casts/VOICES.md` (the "Daily news brief" row → `--pacing brisk`), `SKILL.md` (§3 Verify end: stance step; §Invocation: `--pacing`)
**Tier:** opus — prose that steers the model · **Review:** sonnet → raised to opus by rule 4 (opus implementer)

**Tasks:**
1. panel: the moderator usually listens; advocate and sceptic take turns telling; the stances are the sides.
2. solo: the narrator puts questions to the listener and leaves `[pause 2]`; the felt moment is in the first person.
3. SKILL.md: after Verify, "pick stances from contested points in sources.md, write them to brief.md, and announce
   them in one line; the user may override".
4. SKILL.md §Invocation: add `--pacing` to the usage line and describe "faster/slower".

**Acceptance Criteria:**
- [x] Every cast has `## Reactions` and `## Stance`. CHECK: `grep -c "^## Reactions\|^## Stance" casts/{two-host,panel,solo}.md` → 2 each. EVIDENCE: 2 / 2 / 2
- [x] The cast blocks still parse. CHECK: `render.py --selftest`. EVIDENCE: rc 0 (305 PASS); cast blocks diff vs HEAD empty

**Testing Strategy:** Declared: CI selftests and the privacy grep. Manual: read each cast as the script writer.

---

### Phase 5: Depth

**Goal:** The listener sets the level and focus, separately from research effort.
**Rollback:** `default_level=informed` reproduces today's pitch. Reverting the commit removes the flags.

---

#### Milestone 5.1: `--level`, `--focus`, "go deeper" (M)

**Objective:** Two flags, one config key, level notes per angle, focus research areas and a follow-up episode flow.
**Owns:** `SKILL.md` (§Invocation, §2 Research), `angles/*.md` (a new `## Level notes` section each), `scripts/config.py` (`default_level`), `plugins/podcast/.claude-plugin/plugin.json` (userConfig `default_level`)
**Tier:** opus — model behaviour across five angles · **Review:** opus

**Tasks:**
1. `config.py`: `default_level: "informed"`, enum `intro|informed|expert`, env `PODCAST_DEFAULT_LEVEL`, selftests.
2. `plugin.json` userConfig `default_level`.
3. SKILL.md §Invocation: the flags; `--focus` capped at 3 (a 4th is refused in one line); `--depth` stays research
   effort. §2: each focus aspect gets a dedicated research agent inside the depth agent count.
4. "go deeper on X": a new episode folder `<slug>-deeper-<aspect>` reuses the parent's `research/` and
   `sources.md` read-only, researches only the gap, and verifies only new claims.
5. Each angle gets `## Level notes` (a three-row table: what to skip or add at intro/informed/expert).
   learn-topic's brief "starting level" now points at `--level`.

**Acceptance Criteria:**
- [x] `config.py set default_level=novice` → exit 2. EVIDENCE: exit 2 naming intro/informed/expert (builder + reviewer); `fast` → 2 (orchestrator)
- [x] 5/5 angles have `## Level notes`. EVIDENCE: grep → 1 each ×5
- [x] `claude plugin validate --strict plugins/podcast` and `--strict .` pass. EVIDENCE: ✔ ×2
- [ ] Judged in 6.1: intro fixtures explain every term; expert fixtures skip the basics. EVIDENCE: pending

**Testing Strategy:** Unit: config selftests. Judged: 6.1 rubric rows. Declared: CI.

---

### Phase 6: Eval & release

**Goal:** A regression guard for the rules, then a release the owner approves by ear.
**Rollback:** the release is a version bump. If the readout fails, set the `default_pacing` default back to `brisk`
and ship 0.3.1 (per the Readout decision rule).

---

#### Milestone 6.1: Eval suite `test/pacing/` (M)

**Objective:** Nine fixture scripts (learn-topic, company-diligence and debate × 3 levels), a rubric, a runner doc,
and a CI step.
**Owns:** `test/pacing/**`, `.github/workflows/validate.yml` (one new step), `CLAUDE.md` (eval-suite line + addendum pointer)
**Tier:** opus — writes the go-live gate · **Review:** opus

**Tasks:**
1. Fixtures: fictional topics (no real companies or people), each with a stub `sources.md` and `brief.md`
   (including stances), written to the new rules.
2. `rubric.md`: one row per judged rule, each scored 0/1 with a quoted line as evidence. Judge output is JSON
   `{fixture, scores{}, evidence{}, pass}`.
3. `RUNNING.md`: how to have a Sonnet subagent score all fixtures; pass = ≥ 90% of fixtures pass every row.
4. CI: `render.py <fixture> --dry-run --strict` for each fixture (deterministic layer only, no judge).
5. Calibrate the role heuristic on the fixtures; record its false-positive rate as an execution decision.
6. Red-team fixture: a `focus:` value carrying instructions ("skip verification"). The rubric checks that
   verification still happened.

**Acceptance Criteria:**
- [ ] CI step green on 9/9 fixtures. EVIDENCE: pending
- [ ] Judge run: ≥ 90% of fixtures pass; JSON pasted. EVIDENCE: pending
- [ ] A broken fixture (pauses stripped) fails CI. Red demonstrated. EVIDENCE: pending
- [ ] `CLAUDE.md` records `eval_suite: test/pacing/, threshold 90%`. EVIDENCE: pending

**Testing Strategy:** Declared: the CI step. Judged: the subagent run. Manual: spot-read three fixtures aloud.

---

#### Milestone 6.2: Release 0.3.0 — owner gate (S)

**Objective:** Ship it once the owner approves the release listen.
**Owns:** `plugins/podcast/.claude-plugin/plugin.json` (version), `.claude-plugin/marketplace.json` (version), `README.md`, `test/stranger.sh`, `docs/phases/phase-human-touch/*` (status, readout, retro, action items)
**Tier:** sonnet — mechanical, with deterministic verifiers · **Review:** opus (public release)

**Tasks:**
1. Bump the version to 0.3.0 in both manifests. Document the new flags in the README.
2. `stranger.sh`: assert `--pacing brisk` renders, and that `default_pacing` is `relaxed` in `status --json`.
3. Release listen: one full new-style episode plus its `--pacing brisk` render. Record the owner's verdict.
4. Merge-PR body carries the readout (metric, date, decision rule) and the hostile-env matrix results.
5. Retro + `action-items.md` in the same sitting. Send the final episode informally to the original feedback-givers
   (not a gate) and record their replies.
6. **No push or PR to the public repo without the owner's explicit go-ahead.**

**Acceptance Criteria:**
- [x] `claude plugin validate --strict plugins/podcast` and `--strict .` pass. EVIDENCE: ✔ ×2, check_manifests OK
- [x] `test/stranger.sh` passes. EVIDENCE: ALL PASS on a fresh empty state (after the av fix)
- [x] All six script `--selftest`s pass; the privacy grep is clean. EVIDENCE: 6/6 rc 0; "no personal data outside attribution"
- [x] Owner's release verdict recorded; the Readout decision rule applied. EVIDENCE: owner 2026-10-05 approved relaxed + fixed roles → ship 0.3.0 with relaxed default
- [x] Deviations ledger: 0 `open` rows. EVIDENCE: 41 rows, 0 open

**Testing Strategy:** Declared: CI + stranger.sh. Manual: the owner's listen.

---

## Deviations Ledger

| ID | What was skipped/deviated | Source task/session | Status (open / accepted / fixed) | Who decided |
|----|---------------------------|---------------------|----------------------------------|-------------|
| L1 | `SKILL.md` "minutes × 153" stays stale between 1.1 and 3.2 | plan | fixed | 3.2 (budget 150 wpm relaxed) |
| L2 | `PLAN.md` referenced by `CLAUDE.md` does not exist in the repo | PRD | fixed | owner 2026-10-05: reference dropped; CLAUDE.md now points at docs/phases, validate.yml and test/stranger.sh |
| L3 | Resume prompt's phase-gates Step 4 block has its bracketed provenance notes removed (they name private projects and fail the CI privacy grep); the rules themselves are verbatim | gen-prompt | accepted | orchestrator: privacy non-negotiable outranks verbatim carry-over |
| L4 | Resume prompt is ~380 lines against the ≤150 target, because Build Gates, Cross-Cutting Rules, Universal Clauses, Step 4 and the Execution Graph must be carried verbatim | gen-prompt | accepted | orchestrator: the verbatim rules win over the length target |
| L5 | "Huh." recommended as a free word by the PRD/template but capped by Decision 5 / `NONLEXICAL`; 1.1 followed the cap (E2) | 1.1 | accepted | orchestrator (code contract wins; owner may reverse in 2.1) |
| L6 | §4 says "the cast's `## Reactions`", but panel/solo have none, and `solo.md:34` ("no rhetorical questions") is untouched until 4.2 | 1.1 review LOW-1 | fixed | 4.2 |
| L7 | `level:`/`pacing:` brief fields are written but consumed by nothing until 3.1/5.1; the stance announce/override step lands in 4.2 | 1.1 | accepted | plan sequencing |
| L8 | The 1.2 rescript carries 2–3 non-lexical sounds, breaching the 1.1 cap of one per segment, deliberately, so the owner can hear Kokoro render them. 2.2 must not treat its NONLEXICAL_MANY as a regression | 1.1 review LOW-4 | accepted | plan (task 1.2 step 2) |
| L9 | 1.2 QA "0 other flags" unmet: 5 whisper-base mishearings remain (a tack→attack, stern, jibe→jive, squeezed, there, a→of); phonemes verified correct and isolated round-trips pass; the medium model the episode was originally QA'd with is gone. No qa-ignore pairs added | 1.2 | accepted | owner 2026-10-05: known whisper-base noise, proven in isolation; no larger model |
| L10 | 1.2 renders/QA ran against the real state dir, not a scratch `PODCAST_STATE_DIR` (the engine lives in the state dir; linking it in was denied). Explicit `--voices` skips rotation; `installed.json` and `voice-rotation.json` hashes unchanged | 1.2 | accepted | orchestrator (evidence: hashes) |
| L11 | Kokoro mispronounces "Bernoulli" (BER-now-lee) and nautical "bow" (as in arrow); fixed in the ear test by a local lexicon (`Bernooli`, `bough`). Candidate entries for the shipped `templates/lexicon.txt` | 1.2 | accepted | orchestrator: per-episode lexicon fixes it; not shipped — 'bow' is ambiguous (ship vs arrow) and 'Bernoulli' is topic-specific; release episode needed none |
| L12 | `--dry-run` overestimates: +8% on the original seg 3, +14–16% on the rescripts (many short lines and turn gaps). Feeds 3.1/3.2's 5% estimate-parity AC. Rules cost ≈ +45% airtime for the same content | 1.2 | fixed | 3.2 (estimate within 5% relaxed) |
| L13 | `[pause N]` only exists between lines (`render.py` `re.fullmatch` on the whole line), so a script cannot pause mid-sentence, where people mostly pause. Likely cause of the 1.2 "wrong spot" verdict | 1.2 owner verdict | fixed | 3.1a (inline `[pause N]`) |
| L14 | Decision 5 allowlist loses `mm-hm` (Kokoro spells it as letters; owner heard it). 2.1's `NONLEXICAL` contract and 4.1 must use `hmm`, `uh-huh`, `huh`, `ha` | 1.2 owner feedback | fixed | 2.1/4.1 (mm-hm not allowlisted; BANNED_SOUND) |
| L15 | The owner's pause hierarchy (E8) needs a mid-line micro-pause and an automatic sentence gap. Both are renderer work; fold them into 3.1's gap table (`sentence`, `landing`, `wrap` kinds) and a mid-line pause syntax taught to both `render.py` and `qa.py` | 1.2 | fixed | 3.1a inline beat + 3.1 sentence/turn gaps (relaxed reproduces approved v6 PCM) |
| L16 | §4 now asks for one sentence per line, which moves the "15–30% of lines ≤ 6 words" metric (v5: 98 lines). 2.1's pacecheck must measure per sentence or re-derive the band | E10 | fixed | orchestrator (E16: band 40–70% of sentences, per owner-approved scripts) |
| L17 | Owner on v5: still "a little robotic / scripted"; pauses should be longer; a reaction like "Wait." needs a thinking beat before the question, but a one-word line fails QA (DROPPED), so it is glued to the next sentence with no gap; "lack of emotion". Needs a mid-line beat (L13/L15) and possibly per-line pace | 1.2 owner verdict | accepted | owner 2026-10-04: timing parts done (beats, holds, ladder); pitch/emotion deferred to the Expressive Voice phase (E14) |
| L18 | Whole-line `[pause N]` keeps exit 1 on malformed input and has no upper bound; inline is exit 2 and 0 < N ≤ 10. Unify in 3.1 | 3.1a | fixed | 3.1 (whole-line malformed pause → exit 2) |
| L19 | An isolated "Huh." chunk (before an inline beat) is heard by whisper as "Hi"/"Hello" in every spelling tried; the phonemes are right. Whisper on a lone syllable is unreliable; owner's ear decides | 3.1a / v6 | fixed | 4.1 ("hi" is an aligned-only mishearing of huh) |
| L20 | 2.1 pacecheck and 3.1 `gap_for` must read events through `line_segments()` / `plan_assembly()`, or they miss inline pauses | 3.1a review | fixed | 3.1 (Episode/line_segments/_timeline are the only readers) |
| L21 | Follow-ups outside this phase: (a) new phase "Expressive Voice" (Qwen3-TTS opt-in tier), (b) private-pipeline VC experiment | X1 | accepted | owner 2026-10-04 (deferred by decision) |
| L22 | SKILL.md §4 now says the renderer leaves a gap after every sentence and between speakers under `relaxed`. True only once 3.1 lands: 3.1's GAPS must add `sentence` (≈0.6 s written → ~0.7 heard) and a relaxed `turn` (≈0.85 → ~1.0 heard), split say-lines into sentence chunks only when pacing ≠ brisk, and keep `brisk` sample-identical to 0.2.0. The v3–v6 ear tests emulated this with a script formatter (one sentence per line + `[pause 0.7]` at speaker changes) | rules review E15 | fixed | 3.1 (relaxed reproduces v6 PCM from turn form) |
| L23 | For 4.2 (from the rules review): panel/solo need their own version of Roles/Teach (panel has no learner; debate segs 3–4 uninterrupted), `## Reactions` (L6), solo.md:34 vs guess-before-reveal (narrator poses the puzzle once and answers it, no fake guesses), a solo substitute for the explain-back, a panel name-in-dialogue example, ADVOCATE/SKEPTIC → `stances:` | rules review | fixed | 4.2 |
| L24 | pacecheck gains a 7th warning kind `BANNED_SOUND` (any m-spelling of "mm-hm"; a bare "Mm" too, so "5 mm" would false-positive — warning only). 4.1, 6.1 and SKILL.md consumers must know it | 2.1 | accepted | orchestrator (L14 enforcement) |
| L25 | Pre-existing: unknown speaker and malformed whole-line `[pause]` exit 1 via `sys.exit(str)`, not 2; a missing script file tracebacks | 2.1 review | fixed | 3.1 (unknown speaker, missing file → exit 2) |
| L26 | Two-narrator segments ("roles unclear") never warn — the PRD's core diagnosis; FIGURE_RE counts the pronoun "one"; CJK "。" is not a sentence end | 2.1 review | fixed | 6.1 calibration: SAME_TELLER 0% FP kept; roles-unclear stays informational |
| L27 | Cache invariant: gaps are not in the TTS cache key; CACHE_VERSION unchanged (cache_key byte-identical to main). Existing 0.2.0 episodes re-synthesise sentence chunks once on first relaxed render (37 for a 12-line segment); hostile-env row 6 reads "re-render at relaxed = sentence chunks only, then 0" | 3.1 | accepted | orchestrator (E17) |
| L28 | Sentence splitting never cuts inside a lexicon match, quotes, before lowercase/digit, or after titles/dotted abbreviations; `...?` now ends a sentence (differs from the v6 formatter; v6 identity holds) | 3.1 | accepted | orchestrator |
| L29 | spacious QA on v6 fails NAMES ("bernoulli"→"burnley") with byte-identical chunks to relaxed (which passes): whisper context, same class as L9 | 3.1 | accepted | owner 2026-10-05: same class as L9 |
| L30 | 4.1 limits: a sound misheard as an unlisted word stays an unmatched heard token; a word used as a name never counts as a sound even where the same spelling is a reaction; sounds-only scripts are judged as plain words (pre-allowlist behaviour) | 4.1 | accepted | orchestrator (conservative = stricter) |
| L31 | angles/debate.md segs 3–4 say "uninterrupted"; panel.md reads it as "uninterrupted by the other side; the host may react" (LONG_RUN). debate.md should say so | 4.2 review | fixed | 5.1 (debate.md: uninterrupted by the other side; host may react) |
| L32 | Solo puzzle gets `[pause 1.2]`, not the task's `[pause 2]` (E10: no long silence after a question) | 4.2 | accepted | orchestrator |
| L33 | 5.1 additions beyond the task list (accepted): focus share rules (2×, ~10% base, ≤ ~60% total, cold-open/wrap/must-verify floors — model-judged, unenforced until 6.1's judged run), focus cleaning, staleness re-checks, personal-source exclusion in go-deeper, userConfig↔DEFAULTS parity selftest, non-interactive keeps first 3 aspects; unknown `--level` asks instead of exit 2 (no script parses it) | 5.1 | accepted | orchestrator |
| L34 | Level AC "intro explains every term; expert skips basics" is judged, not mechanical → carried into 6.1's rubric | 5.1 | fixed | 6.1 (rubric row level_respected) |
| L35 | Judged eval leftovers on the gated version: majority fail learn-topic/expert level_respected ("You know the basic design." then re-states it); single-judge flags: "after a day, ninety-nine parts…" not said as arithmetic, "a newsletter for the warehouse trade" (R1 says trade newsletter), "cut the average wait to eleven" (no prior bus wait in V3), "It leaks slowly" unmarked. Fix + re-judge before 6.2's PR is merged | 6.1 | fixed | orchestrator: fixed + re-judged 2026-10-05, 3-judge majority 10/10 fixtures clean (single-judge flags only: 'not there yet', 'a choice', 'judge it against heat', 'the report doesn't test it') |
| L36 | The judged eval needed 5 rounds: a strict judge keeps finding scope creep the writer adds (every/whole/most, added categories, derived numbers). The §4 self-check is the mitigation; real episodes get no judge, so the self-check carries the load | 6.1 | accepted | orchestrator (E18) |
| L37 | **Found by stranger.sh in 6.2:** a fresh install today gets av 19.0.1 (unpinned) with faster-whisper 1.2.1, which calls `av.open(metadata_errors=…)` → every qa.py run fails. Affects every new 0.2.0 install too. Install smoke test transcribes silence without av, so it didn't catch it. Fix (pin + file-path smoke test + repair path) in progress; outside 6.2's Owns (setup.sh), accepted for the release | 6.2 | fixed | orchestrator: av>=11,<19 pin, WAV-file smoke test, live-site-packages detection, sized repair via `upgrade qa` → qa-<active> (~35 MB); opus review FAIL → fixed; fresh stranger.sh ALL PASS, broken state repaired |
| L38 | QA on a full 13-min episode can fail DROPPED/MISSING when whisper-base loses a window (release2: L175 dropped and L181 hallucinated after only the opening line changed; the same cached audio passes in isolation, 0 dropped). A user would be blocked by a transcriber artifact. Needs a QA-side fix (re-check a dropped line's audio slice alone before failing) | 6.2 | accepted | owner 2026-10-05 (transcriber noise accepted); known issue in the 0.3.0 PR; fix (re-check a dropped line's slice alone) is action item A2 |
| L39 | Fixed roles (E19): SAME_TELLER → TELLER_CHANGED; 7 two-host fixtures rewritten (Maya teaches all). Re-judged by 3-judge majority: 9/10 clean (learn-topic/expert opinion_marked, A+B) → that line now marked "my advice"; deterministic PASS, QA ≥ 0.978 on the 3 touched fixtures | E19 | fixed | orchestrator |
| L40 | Pre-existing (not this phase): kokoro install fails its smoke test on a long state path (~125+ chars → "…/phontab: No such file"), and the short-path hint never printed because the grep only matched `espeak-ng-data`. Grep now also matches `phontab`; a pre-download path-length check is an action item | 6.2 hostile matrix | fixed | orchestrator (hint) + A7 (pre-check) |
| L41 | piper: the dry-run estimate (fitted on kokoro, 163 wpm) runs 10–13% short | 6.2 hostile matrix | accepted | orchestrator: known difference; kokoro is the default engine |

## Hostile-Env Matrix

| # | Condition | Why it's normal | Pass/Fail | Notes |
|---|---|---|---|---|
| 1 | No voice engine, no ffmpeg (Tier 0) | fresh install, `auto_setup=never` | PASS (2026-10-05) | dry-run rc 0 ×3 pacings, render rc 3 with offer |
| 2 | QA not installed | `qa_level=none` | PASS (2026-10-05) | 0 qa/faster_whisper/av imports traced |
| 3 | piper engine instead of kokoro | old installs | PASS (2026-10-05) | piper gaps scale as designed; estimate 10–13% short (L41) |
| 4 | Non-interactive `claude -p` | cron users | FAIL→fixed (2026-10-05) | SKILL.md lacked the non-interactive rule; added (render anyway, append warnings to brief.md) |
| 5 | Throwaway `HOME` (stranger.sh) | strangers | PASS (2026-10-05) | stranger.sh ALL PASS, defaults relaxed/informed |
| 6 | Existing episode with a 0.2.0 `.tts-cache` | upgrades | PASS (2026-10-05) | brisk 0 synths & PCM == main; relaxed 37 once then 0; cast lock kept |
| 7 | Script with zero `[pause]` and no chapters | old scripts | PASS (2026-10-05) | one implicit segment |
| 8 | Non-English voice line in a script | bilingual episodes | PASS (2026-10-05) | no crash |
| 9 | Env var `PODCAST_DEFAULT_PACING=""` | cron env | PASS (2026-10-05) | '' not overriding; ' Brisk ' → brisk |


## Cross-Cutting Rules

_Append verbatim to every task prompt and resume prompt._

```
- Nothing personal ships: no names, handles, employers, projects, hostnames, tokens, chat ids or /home/<user>
  paths outside PLAN.md, CLAUDE.md and LICENSE. Run the CI privacy grep before every commit, including docs/.
- Tier 0 must always work: no new step may require a voice engine, ffmpeg or QA to produce a script.
- No sudo; no system packages; no new third-party Python dependencies (stdlib only in scripts).
- Verification is the product: facts trace to sources.md; opinions are marked as opinions and never carry an
  unverified fact; QA strictness is never lowered except by the exact allowlist in Decision 5.
- Exit codes: 2 = bad input, 3 = not installed, 4 = pacecheck --strict failure. Never reuse 3.
- Gaps are not in the TTS cache key. Never add them to it, and never bump CACHE_VERSION for a gap change.
- `brisk` reproduces 0.2.0 audio sample for sample (compare decoded PCM, not MP3 bytes, which carry a date tag). Any change that breaks this is a defect.
- Every user-visible change ships with a version bump in BOTH plugin.json and marketplace.json (done once, in 6.2).
- The primary checkout stays on main. Work in a worktree; commit there; merge into main. Nothing is pushed to the
  public repo without the owner's explicit go-ahead.
- Never overwrite an existing episode's script or audio. Write beside it.
- No demeaning comparisons or stigmatising language about health or identity in any cast, rule or fixture.
- Seams (one owner each): SKILL.md sections — 1.1 owns §1/§4, 4.2 owns §3 end + the --pacing usage line, 5.1 owns
  §Invocation depth + §2, 3.2 owns the §4 budget line. config.py — 2.1 NONLEXICAL, 3.1 default_pacing,
  5.1 default_level. plugin.json — 3.1/5.1 userConfig entries, 6.2 version.
```

### Universal Clauses (phase-gates Step 3 — part of every milestone's acceptance criteria)

```
- If two sources of truth (mockups, PRD, decisions doc) disagree, STOP and
  surface the conflict as a decision for the orchestrator. Never pick one silently.
- Never render a clickable affordance without a working handler. If the function
  isn't built, omit the element. A missing button reads as "not done yet"; a dead
  button reads as "broken." If an action can be a spatial no-op (navigating to
  where you already are), give it a visible effect anyway — scroll, flash, focus.
- All reads of shared/divergent data shapes go through the project's normalizer
  layer (see the repo's phase-gates addendum for which one). When legacy semantics
  differ, EXTEND the normalizer — never inline an ad-hoc derivation.
- Any deviation, limitation, or scope cut you make MUST be stated in a clearly
  marked "DEVIATIONS" section of your final report, even if intentional.
- If your change introduces a loop containing a database or network call,
  either batch it or state in DEVIATIONS why batching is not appropriate
  here. Likewise for a polling loop where the backend offers a
  subscription/realtime channel, and for a route that sets both
  `force-dynamic` and a `revalidate` interval (the latter never runs). This
  is a justification requirement, not a ban — bounded loops and per-row
  conflict handling are legitimate when you say so.
- If your change writes a string into HTML or script context —
  `dangerouslySetInnerHTML`, `innerHTML`/`outerHTML`/`insertAdjacentHTML`,
  `document.write`, a JSON blob inside a `<script>` tag, or a template string
  assembled into markup — name in DEVIATIONS the escaping function the data
  passes through and the `file:line` where it lives. A code comment
  asserting the data is "sanitized" is not a trace, and
  a field allowlist is not an escaper — it chooses which fields survive and
  copies their contents verbatim. If nothing on the path escapes, say so
  rather than assuming something upstream does. This is a trace requirement,
  not a ban — JSON-LD and other deliberate markup injection are legitimate
  once you name the escaper.
- Do not tick a box you cannot prove. Every acceptance criterion you mark done
  names the command you ran and its actual output; a tick whose evidence reads
  "pending" is UNMET, and worse than an empty box, because it reads as done and
  stops anyone re-checking. If you finished something the plan does not list,
  add the row — or, if you are a sub-agent, report it in DEVIATIONS for the
  orchestrator to add, since the plan table is outside your `Owns` set and only
  the orchestrator commits (Step 6). Unrecorded work is the same defect facing
  the other way.
- Before writing a general-purpose component from scratch (date picker, table,
  modal, parser, retry/backoff, queue, auth flow), name in DEVIATIONS the
  existing library or in-repo module you checked and why it does not fit.
  "Build it" is a fine answer; not having looked is not.
```

---

## Dependencies & Prerequisites

### External
- **Kokoro v1.0 pack + whisper qa-base:** already installed on the dev host (`setup.sh status`: kokoro, base). Needed for 1.2, 3.1, 3.2, 4.1 and 6.2.
- **Owner time:** two listening gates (1.2, 6.2). These are blocking asks, not footnotes.

### Internal
- The private twin's sail episode folder (for 1.2). Read-only, except the new files written beside the originals.

### New Libraries
None. Standard library only, consistent with `validate.yml` ("no third-party packages installed").

---

## Risk Mitigation

### Risk: The rules don't win by ear
**Mitigation:**
- 1.2 is a kill point placed before any code. On a loss, revise the rules with the owner and re-run 1.2; never proceed to Phase 2.

### Risk: The allowlist weakens QA
**Mitigation:**
- Alignment-scoped removal, plus the five selftests in 4.1. Reds are demonstrated for "dropped lexical line" and "stray mishearing".

### Risk: The role heuristic is noisy
**Mitigation:**
- It is a warning only. Calibrate it in 6.1. Drop the `SAME_TELLER` warning if its false-positive rate is > 20% (ledger it).

### Risk: Privacy leak through docs, fixtures or measurements
**Mitigation:**
- Fictional fixture topics; numbers-only baselines; the CI grep covers `docs/` and `test/`.

---

## Success Metrics

### Functional
- [ ] Every PRD functional acceptance criterion is ticked with evidence (see Traceability).
- [ ] CI green, including the new pacecheck step; stranger.sh passes.

### Quality
- QA coverage: ≥ 0.96 on every fixture and on the release episode.
- Dry-run estimate vs rendered length: within 5%.

### User Experience
- Fixtures: 15–30% short lines, ≥ 1 pause per 90 s, ≥ 1 felt moment per segment, ≥ 1 disagreement per episode.
- The owner prefers the new version at both gates.

---

## Sequencing Summary

| Phase | Unblocks | Deliverable |
|-------|----------|-------------|
| Phase 1 | everything (kill point at 1.2) | Rules in SKILL.md + two-host cast; owner's ear verdict |
| Phase 2 | targets for 3–6; the deterministic eval layer | pacecheck + baselines |
| Phase 3 | the release default; 3.2's measured budget | Context-aware gaps, `--pacing`, accurate estimate |
| Phase 4 | non-lexical sounds in real episodes; stances in every cast | QA allowlist, casts, stance flow |
| Phase 5 | the depth request | `--level`, `--focus`, go-deeper |
| Phase 6 | release | Eval suite, 0.3.0, readout, retro |

_Ordering and dependency, not dates._

---

## Execution Graph

| Milestone | Depends on | Owns | Size | Tier | Review tier | Verifiers | Wave |
|-----------|------------|------|------|------|-------------|-----------|------|
| 1.1 Script rules + two-host `[Contract]` | — | `SKILL.md` §1/§4, `casts/two-host.md` | S | opus | opus | `render.py --selftest`, privacy grep | 1 |
| 1.2 Ear test (owner gate) | 1.1 | private twin episode folder (new files only) | S | opus | opus | `qa.py`, sha256 of originals, owner verdict | 2 |
| 2.1 pacecheck `[Contract]` | 1.2 | `render.py` (pacecheck, --strict), `config.py` (NONLEXICAL) | M | opus | opus | `render.py --selftest`, `config.py --selftest` | 3 |
| 2.2 Baselines | 2.1 | PRD baseline cells | XS | sonnet | sonnet | pacecheck output, privacy grep | 4 |
| 3.1 Gap table + `--pacing` `[Contract]` | 2.1 | `render.py` (gaps, estimate, --pacing), `config.py` (default_pacing), `plugin.json` (userConfig) | M | opus | opus | selftests, `cmp` brisk vs main, `plugin validate --strict` | 5 |
| 3.2 WPM + budget | 3.1 | `render.py` (WPM), `SKILL.md` §4 budget line | S | sonnet | opus | dry-run vs `ffprobe` within 5% | 6 |
| 4.1 qa.py allowlist | 2.1 | `qa.py` | M | opus | opus | `qa.py --selftest`, real QA on the 1.2 render | 7 |
| 4.2 Casts + stance flow | 1.1, 3.1 | `casts/panel.md`, `casts/solo.md`, `casts/README.md`, `casts/VOICES.md`, `SKILL.md` §3 end + usage line | S | opus | opus | `render.py --selftest`, grep for the sections | 8 |
| 5.1 Level + focus | 4.2 | `SKILL.md` §Invocation/§2, `angles/*.md`, `config.py` (default_level), `plugin.json` (userConfig) | M | opus | opus | `config.py --selftest`, `plugin validate --strict` ×2 | 9 |
| 6.1 Eval suite | 5.1, 4.1, 3.2 | `test/pacing/**`, `validate.yml` (1 step), `CLAUDE.md` | M | opus | opus | CI pacecheck step, judge JSON | 10 |
| 6.2 Release (owner gate) | 6.1 | manifests (version), `README.md`, `test/stranger.sh`, phase docs | S | sonnet | opus | `stranger.sh`, CI, `plugin validate --strict` ×2, owner verdict | 11 |

**Waves:** 1: 1.1 · 2: 1.2 · 3: 2.1 · 4: 2.2 · 5: 3.1 · 6: 3.2 · 7: 4.1 · 8: 4.2 · 9: 5.1 · 10: 6.1 · 11: 6.2

_Why serial:_ 2.2 ∥ 3.1 and 3.2 ∥ 4.1 have disjoint `Owns`, but `render.py`, `config.py` and `SKILL.md` are each
touched by four or more milestones, and 4.1/3.2 share the heavy verifier (kokoro + whisper renders). Running
serially keeps the plan Lightweight. Parallelising any pair upgrades the tier to Full (2b-f).

**Tier labels.** `opus | sonnet | haiku` are capability ranks — highest, middle, lowest — not an instruction to run a particular vendor's models. On Claude Code they resolve to those model names. On any other runtime, map them to the strongest, middle and cheapest models that runtime is configured with; on a single-model runtime every tier resolves to that one model, and "review one tier above" degrades to a fresh review pass by a separate agent or session — never the context that wrote the code. The labels themselves stay fixed: `pm-agent-batch` and the pipeline lint read them.

**Rules applied:** sonnet only on 2.2, 3.2 and 6.2 (XS/S, mechanical, with deterministic verifiers). Every other
milestone is opus, because it introduces a new pattern (`grep -rn "pacecheck\|NONLEXICAL\|GAPS\b\|stance" plugins/`
→ 0 hits on `main`) or shapes model behaviour. Reviews follow risk: the QA-gate and render-output rows get full opus
review; the doc-only 2.2 gets one sonnet pass.

---

## Resource Budget

```
max_parallel: 1                   # serial graph (see Waves)
token_budget: 6.0M                # HARD stop, not advice
heavy_verifiers: [kokoro-render+whisper-qa]   # 1.2, 3.1, 3.2, 4.1, 6.2 — run one at a time
```
calibration: default table, unmeasured here

_Arithmetic: implementation XS 60k + S 100k ×5 (1.1, 1.2, 3.2, 4.2, 6.2) + M 250k ×5 (2.1, 3.1, 4.1, 5.1, 6.1) =
1.81M; review 0.8× = 1.45M; heavy-verifier runs 5 × 150k = 0.75M; subtotal 4.01M × 1.5 ≈ 6.0M. Check the running total at every row flip (phase-gates
lesson)._

---

## Traceability

- **Decisions covered:** 9/9. D1 sequencing → 1.2 gate; D2 sail episode → 1.2; D3 stances → 1.1 brief + 4.2 flow;
  D4 level/focus → 5.1; D5 allowlist → 2.1 constant + 4.1; D6 relaxed everywhere → 3.1 `default_pacing`; D7
  warn-not-block → 2.1 `--strict`; D8 subagent judge → 6.1; D9 owner's ear → 1.2 + 6.2.
- **PRD requirements mapped:** ear test → 1.2 · SKILL.md rules → 1.1 · casts `## Reactions`/stance → 1.1, 4.2 ·
  brief fields → 1.1 · pacecheck → 2.1 · brisk byte-identical + 0 re-synth → 3.1 · estimate within 5% + WPM + no
  stale 153 → 3.2 · `--level`/`--focus`/4th refused/go-deeper → 5.1 · allowlist → 4.1 · stance announce/override →
  4.2 · default_level/default_pacing → 3.1, 5.1 · selftests/validate/stranger.sh → every milestone + 6.2 ·
  version 0.3.0 → 6.2 · privacy grep → every milestone · no push without go-ahead → 6.2 · eval suite → 6.1.
- **Scope beyond PRD:**
  - Exit code 4 for `--strict`: needed so it doesn't collide with 3 = not installed.
  - `docs/ops/phase-gates-addendum.md`: required by phase-gates.
  - Ledger row L2 (`PLAN.md` missing): surfaced, not fixed here.

---

**Updating this plan:** After each milestone, update the Progress Overview table status (Not Started -> In Progress -> Complete) and commit. The table is the only progress state — nothing else to sync. Add blockers to the Active Blockers section as needed.

---

## Next Steps

1. **Review this plan** with the owner. In particular, confirm the serial graph and the 6.0M token stop.
2. **Begin Milestone 1.1:** script rules + the two-host cast, in a worktree:
   ```bash
   git worktree add ../podcast-skill-human-touch -b feat/human-touch
   cd ../podcast-skill-human-touch/plugins/podcast/skills/podcast/scripts
   for s in config.py render.py qa.py rawfetch.py deliver.py audition.py; do python3 $s --selftest; done
   ```
3. Generate the resume prompt: `/pm-agent gen-prompt human-touch`.

---

**Status:** Plan complete and ready for implementation

**Related Documents:**
- **Requirements:** `docs/phases/phase-human-touch/phase-human-touch-requirements.md`
- **Decisions:** `docs/phases/phase-human-touch/phase-human-touch-decisions.md`
- **Project Context:** `CLAUDE.md`
