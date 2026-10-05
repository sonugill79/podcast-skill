# Task Prompt — Phase Human Touch, Milestone 1.2

You are the sub-agent implementing ONE milestone. The orchestrating session owns the plan, the Progress table and every commit.

- **Plan:** `docs/phases/phase-human-touch/phase-human-touch-implementation-plan.md` · **Decisions (locked):** `docs/phases/phase-human-touch/phase-human-touch-decisions.md` · **PRD:** `docs/phases/phase-human-touch/phase-human-touch-requirements.md`
- **Hazards & Verify-First:** read that section of `docs/phases/phase-human-touch/phase-human-touch-resume-prompt.md` before you start.
- Write ONLY inside this milestone's **Owns** set. Do not edit the plan's Progress table, and do not commit. Leave your changes in the working tree for the orchestrator.
- The plan is a hypothesis, and so are these instructions. The orchestrator's error rate is not lower than yours. Report every instruction-versus-reality mismatch as a finding, and refuse on the merits when an instruction is wrong.
- Final report: what changed (files), every acceptance criterion with its CHECK command and actual EVIDENCE output, and a **DEVIATIONS** section (write "none" if there are none).

## Phase context

### Phase 1: Prove by ear
**Goal:** Find out whether the script rules alone make an episode sound human, before writing any code.
**Rollback:** revert the SKILL.md/cast commit. No code ships in this phase.

## Milestone (verbatim from the plan)

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
- [ ] The original script and audio are untouched. CHECK: `sha256sum script.txt *.mp3` before and after. EXPECT: identical. EVIDENCE: pending
- [ ] Every factual line in the rescript maps to a `sources.md` entry (a reviewer table: line → source). EVIDENCE: pending
- [ ] QA: 0 flags outside the listed non-lexical lines. EVIDENCE: pending
- [ ] **Owner verdict recorded:** prefers humanized → continue · prefers original → STOP, mark Blocked "I need a rules revision decision from the owner". EVIDENCE: pending
- [ ] Owner's note on how the non-lexical sounds sounded, recorded (this feeds 4.1). EVIDENCE: pending

**Testing Strategy:**
- **Unit Tests:** none.
- **Integration Tests:** `qa.py` on the rendered rescript.
- **Manual Verification:** the owner's A/B listen. This is the gate.
- **Declared Verifiers:** `qa.py` exit code (expected non-zero only on the listed lines).

---

## Cross-Cutting Rules (verbatim — apply all of them)

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

## Universal Clauses (verbatim — apply all of them)

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
