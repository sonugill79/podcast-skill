# Phase Human Touch: Resume Implementation Prompt

**Purpose:** Use this prompt to have an AI agent resume Phase Human Touch implementation from wherever it was last left off.

**Last Updated:** 2026-10-03

---

## Standard Resume Prompt

Copy and paste this prompt when starting a new session:

```
I'm working on Phase Human Touch for this project.
Please help me resume implementation from wherever I last left off.

## Your Tasks:

1. **Read the implementation plan:**
   - Location: docs/phases/phase-human-touch/phase-human-touch-implementation-plan.md
   - Pay special attention to:
     - "Progress Overview" table — the single source of truth; current milestone = first non-Complete row
     - "Active Blockers & Issues" section (shows known problems)
     - Any gate criteria on locked phases (do not start gated work): **1.2 and 6.2 are owner listening gates**
     - The current milestone section with task details

2. **Read the decisions document:**
   - Location: docs/phases/phase-human-touch/phase-human-touch-decisions.md
   - This has all architectural decisions that are locked in
   - Reference these when implementing to ensure consistency

3. **Understand the current state:**
   - Tell me what milestone we're currently on
   - What tasks are complete vs incomplete
   - What the next immediate task is
   - Any blockers or issues I should know about

4. **Propose next steps:**
   - What specific task should I work on next?
   - What files need to be created/modified?
   - What code should be written?
   - Are there any dependencies I need to handle first?

5. **As we work together:**
   - Help me implement the current task
   - Remind me to update the implementation plan after completing each task
   - Check off completed subtasks: - [x]
   - Update the Progress Overview table: Not Started -> In Progress -> Complete
   - Add notes about decisions made or issues encountered
   - Treat `[Contract]`-tagged code as locked interfaces; `[Sketch]` as free to reshape

## Important Context:

- A Claude Code plugin + its own marketplace. Python 3 standard-library scripts (`plugins/podcast/skills/podcast/scripts/`), a bash installer, Markdown skill/casts/angles. No package manifest; CI = `.github/workflows/validate.yml`.
- Non-negotiables (CLAUDE.md): nothing personal ships (CI privacy grep); Tier 0 always works; no sudo; verification is the product; bump `version` in BOTH manifests for any user-visible change.
- Every script has an offline `--selftest`; run all six after any change. Validate with `claude plugin validate --strict plugins/podcast` and `--strict .`.
- The primary checkout stays on `main` (a hook blocks commits there). Work in a worktree. Never push to the public repo without the owner's explicit go-ahead.
- Settings flow through `config.py` (DEFAULTS / ENUM_CHOICES / ENV_OVERRIDES); `render.py` and `qa.py` each parse the script, so a new syntax is taught to both.
- Locked decisions (one-liners; the decisions doc is canonical):
  - D1: rules first, proved by ear (1.2) before any renderer code. 1.2 losing = STOP.
  - D2: ear test = segment 3 of the private twin's sail episode; write beside the original, never over it.
  - D3: the agent picks host stances from contested points in sources.md, announces them in one line, and the user can override.
  - D4: `--level intro|informed|expert` + `--focus` (≤ 3); `--depth` stays research effort.
  - D5: non-lexical sounds are allowed via a `qa.py` allowlist (optional tokens); ≤ 1 per segment, never alone on a line; all other QA gates unchanged.
  - D6: `default_pacing=relaxed` for EVERY cast, solo included; `--pacing brisk` = 0.2.0 audio.
  - D7: pacecheck warns (exit 0); the agent must revise flagged segments; `--strict` → exit 4.
  - D8: judged eval = a Claude Sonnet subagent at dev time, scoring `test/pacing/rubric.md`, ≥ 90% of fixtures.
  - D9: readout = the owner's ear (1.2 and 6.2); feedback-givers get the final episode informally, not as a gate.

## Build Gates (must satisfy before this phase ships):

### Gate: Validation
- [x] Demand signal: three independent feedback themes (pace, emotion, point of view) plus a depth request, all from existing listeners
- [ ] Kill criterion: if the owner's Milestone 1.2 A/B by ear doesn't prefer the rescripted segment, stop before any renderer work. If the owner rejects the release listen, make `brisk` and the 0.2.0 rules the default and keep the new rules opt-in

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

### Gate: Documentation (the 6 docs)
- [x] PRD  [ ] TRD (decisions doc)  [ ] App Flow (N/A; covered by the UX flows)  [ ] UI/UX Brief (N/A)  [ ] Backend Schema (N/A; only new `brief.md` fields)  [ ] Implementation Plan

## Phase Gates (process — tier: Lightweight):

Repo-specific rules: docs/ops/phase-gates-addendum.md. Upgrade to Full if any wave is parallelised.

### Cross-Cutting Rules (verbatim)

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

### Universal Clauses (verbatim)

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

### Execution-time gates (phase-gates Step 4, verbatim except that bracketed provenance notes naming private projects are removed for the privacy gate)

1. **The deviations ledger — "noted" is not "done."** The moment any report (an agent's final report, or your own mid-session note) discloses a deviation, limitation, or scope cut, append it to the ledger **before starting the next task**. This is the single highest-value gate: in the source retro, four of the first five user-testing findings were already written down in reports that scrolled away — and a single agent's context compaction loses disclosures the exact same way.
   - Row format: `| ID | What was skipped/deviated | Source task/session | Status (open / accepted / fixed) | Who decided |`
   - `accepted` requires an explicit recorded decision — not silence.
   - **Gate: user testing does not start while any row is `open`.**

2. **The decision log — the coder's decisions, not just the planner's.** Grooming produces `phase-{name}-decisions.md`; execution produces decisions the plan didn't anticipate, and those are the ones that get lost. Whenever you choose between approaches mid-task, append to that same decisions doc under `## Execution decisions`: *problem · why it matters · options considered · choice · trade-off accepted*. A task is not closeable while a non-trivial choice was made and not logged — the reviewer should be able to explain the change back without reading the diff. Same-sitting rule as the ledger: log before starting the next task.

3. **Require a demonstrated red, not a green suite.** For every assertion group, the executing agent mutates the thing under test, shows the test fail, reverts, and confirms the file is byte-identical. **Hunt specifically for assertions that pass without being able to fail** — they are worse than no test, because they manufacture confidence. Watch for: a guard whose failure the code under test swallows; a drift check blind at the moment a literal is *introduced*; a test pinning a bound that later moves, still passing because the fixture is far from it; a suite that exercises one input shape while the change affects another; and **a test that imports the same constant the code imports, so mutating it moves both sides and nothing goes red** — mutate the consumer, never the shared source.

4. **Seam sweep after every parallel wave (Full tier).** One agent, whole-surface scope, standing checklist — findings fixed next wave or ledgered as explicit `accepted` rows:

```markdown
# Seam Sweep — wave <N>, <date>
- [ ] Fixed/floating element collisions at every breakpoint (list fixed elements: …)
- [ ] Every shared component's props verified at every call site (list: …)
- [ ] State interactions between features rendering in the same region (list: …)
- [ ] One brand mark, one icon language, one empty-state idiom across new surfaces
- [ ] Every interactive element clicked once — zero dead affordances
- [ ] New entries for the deviations ledger: …
```

5. **Hostile-environment matrix before user testing (both tiers).** Type checks and unit tests are environment-free; a friendly-config QA pass misses what the real dev setup does daily. One headless-browser pass per row. Generic starter rows (extend with the repo addendum's project-specific rows):

```markdown
| # | Condition | Why it's normal | Pass/Fail | Notes |
|---|---|---|---|---|
| 1 | Plain-HTTP / non-secure origin | LAN-IP dev browsing | | clipboard, secure-context APIs |
| 2 | Dev-mode double-effects (React StrictMode etc.) | Dev default | | effect/ref-guard deadlocks |
| 3 | Every optional API key absent | Fresh checkout | | fallbacks must exist |
| 4 | Empty / minimal data | New users start empty | | empty states |
| 5 | Smallest-cardinality state (single member, one item) | Common real state | | |
| 6 | Every reachable "unusual" state (locked + empty, etc.) | Reachable = real | | |
```

Extend the matrix when a new hostile condition is discovered — don't fix the one bug and move on.

6. **Look at the rendered page. A screenshot is a different CLASS of evidence from an assertion** — an assertion checks what you thought to ask; a screenshot shows what you didn't. For any UI change, render it and read the image before calling it done, and again after each fix. Whole categories of defect are invisible to DOM and measurement *by construction*:
   - **Right DOM, wrong pixels.** Every element present and correct, one of them sitting on top of another. A dropdown opening by itself covered the control directly beneath it; no query could see that.
   - **Right code path, wrong data.** A logo lookup fell back to "first two letters of the airline name", so `Alaska Airlines → AL` rendered *Malta Air's real logo*. A wrong identifier does not throw — it resolves to somebody else's valid asset. Only a human eye on the image catches it.
   - **Plausible values that are semantically wrong.** An arrival-airport filter offering "Los Angeles" on a Hawaii search. The count was right, the string was a real airport, the code was clean.
   - **Clipped overflow.** `documentElement.scrollWidth` reports **0** when an ancestor clips, while the buttons sit unreachably off-screen. Assert on each element's `getBoundingClientRect().right` against the viewport instead; it catches both the clipped and the scrolling case.
  

7. **Before trusting a green UI check, prove the harness rendered what you think.** A blank page, a redirect, a missing feature-flag cookie and a wrong URL shape all produce a *passing* check of nothing. Assert one sentinel that must be on screen — the specific row, the specific heading — as the first line of the test, and screenshot once while building it.

8. **A ticked box carries its evidence — `pending` plus a tick is worse than an empty box.** Write every gate line, in a plan's AC as in the kickoff checklist below, as `CHECK:` the command or query that decides it · `EXPECT:` the success marker · `EVIDENCE:` its actual output, or `pending` (format from the `unlazy` skill, `Leonxlnx/unlazy`, MIT). Tick only once the evidence is pasted: a tick still reading `pending` is **unmet**, and worse than an untouched box, because it reads as done and stops anyone re-checking. The gate runs the other way too — **a session's last act is flipping its own rows**, in the final commit, or the next session must re-verify everything before it can trust the table. Not hypothetical, and not the executing agents' failure — from this portfolio's own record: seven `pm-agent` Build Gates shipped 2026-07-08 and the index did not know until 2026-08-27; a deletion defect that was one review away from being left as a doc paragraph; an "open: 3 of 12 documents" line in a skill was still quoted after all 15 had shipped, and that one stale sentence was the standing premise of an entire evaluation track; two PRs were asserted open for eight days after `gh pr view` showed them merged. Four instances, one shape — a status nobody had to prove.

9. **Perf-smell sweep over the diff, at review time.** Universal Clause 5 makes the builder justify; this is the half that checks. Over the added lines only (`git diff -U0 <base>..HEAD | grep '^+'`), resolve or record every hit: a write inside a loop (batch it, or `INSERT … SELECT FROM unnest(...) RETURNING id` when the ids feed the next step); two or more independent `await`s in sequence (`Promise.all` / `asyncio.gather`); a query inside a loop over rows just fetched (N+1 — join, or `id = ANY($1)`); `force-dynamic` / `no-store` / `cookies()` newly added to an anonymous public route; `force-dynamic` and `revalidate` in one file (the latter never runs). Diff-scoped by construction, so it cannot drown in pre-existing violations (Step 7 rule 2). A hit is not a defect by itself — a bounded three-item loop is fine — but an unresolved hit may not be silent.

## Execution (how this session runs the graph):

### Execution Graph (verbatim from the plan, plus a task-prompt column)

| Milestone | Depends on | Owns | Size | Tier | Review tier | Verifiers | Wave | Task prompt |
|-----------|------------|------|------|------|-------------|-----------|------|---|
| 1.1 Script rules + two-host `[Contract]` | — | `SKILL.md` §1/§4, `casts/two-host.md` | S | opus | opus | `render.py --selftest`, privacy grep | 1 | `docs/phases/phase-human-touch/phase-human-touch-task-1.1.md` |
| 1.2 Ear test (owner gate) | 1.1 | private twin episode folder (new files only) | S | opus | opus | `qa.py`, sha256 of originals, owner verdict | 2 | `docs/phases/phase-human-touch/phase-human-touch-task-1.2.md` |
| 2.1 pacecheck `[Contract]` | 1.2 | `render.py` (pacecheck, --strict), `config.py` (NONLEXICAL) | M | opus | opus | `render.py --selftest`, `config.py --selftest` | 3 | `docs/phases/phase-human-touch/phase-human-touch-task-2.1.md` |
| 2.2 Baselines | 2.1 | PRD baseline cells | XS | sonnet | sonnet | pacecheck output, privacy grep | 4 | `docs/phases/phase-human-touch/phase-human-touch-task-2.2.md` |
| 3.1 Gap table + `--pacing` `[Contract]` | 2.1 | `render.py` (gaps, estimate, --pacing), `config.py` (default_pacing), `plugin.json` (userConfig) | M | opus | opus | selftests, `cmp` brisk vs main, `plugin validate --strict` | 5 | `docs/phases/phase-human-touch/phase-human-touch-task-3.1.md` |
| 3.2 WPM + budget | 3.1 | `render.py` (WPM), `SKILL.md` §4 budget line | S | sonnet | opus | dry-run vs `ffprobe` within 5% | 6 | `docs/phases/phase-human-touch/phase-human-touch-task-3.2.md` |
| 4.1 qa.py allowlist | 2.1 | `qa.py` | M | opus | opus | `qa.py --selftest`, real QA on the 1.2 render | 7 | `docs/phases/phase-human-touch/phase-human-touch-task-4.1.md` |
| 4.2 Casts + stance flow | 1.1, 3.1 | `casts/panel.md`, `casts/solo.md`, `casts/README.md`, `casts/VOICES.md`, `SKILL.md` §3 end + usage line | S | opus | opus | `render.py --selftest`, grep for the sections | 8 | `docs/phases/phase-human-touch/phase-human-touch-task-4.2.md` |
| 5.1 Level + focus | 4.2 | `SKILL.md` §Invocation/§2, `angles/*.md`, `config.py` (default_level), `plugin.json` (userConfig) | M | opus | opus | `config.py --selftest`, `plugin validate --strict` ×2 | 9 | `docs/phases/phase-human-touch/phase-human-touch-task-5.1.md` |
| 6.1 Eval suite | 5.1, 4.1, 3.2 | `test/pacing/**`, `validate.yml` (1 step), `CLAUDE.md` | M | opus | opus | CI pacecheck step, judge JSON | 10 | `docs/phases/phase-human-touch/phase-human-touch-task-6.1.md` |
| 6.2 Release (owner gate) | 6.1 | manifests (version), `README.md`, `test/stranger.sh`, phase docs | S | sonnet | opus | `stranger.sh`, CI, `plugin validate --strict` ×2, owner verdict | 11 | `docs/phases/phase-human-touch/phase-human-touch-task-6.2.md` |

**Waves:** 1: 1.1 · 2: 1.2 · 3: 2.1 · 4: 2.2 · 5: 3.1 · 6: 3.2 · 7: 4.1 · 8: 4.2 · 9: 5.1 · 10: 6.1 · 11: 6.2

_Why serial:_ 2.2 ∥ 3.1 and 3.2 ∥ 4.1 have disjoint `Owns`, but `render.py`, `config.py` and `SKILL.md` are each
touched by four or more milestones, and 4.1/3.2 share the heavy verifier (kokoro + whisper renders). Running
serially keeps the plan Lightweight. Parallelising any pair upgrades the tier to Full (2b-f).

**Tier labels.** `opus | sonnet | haiku` are capability ranks — highest, middle, lowest — not an instruction to run a particular vendor's models. On Claude Code they resolve to those model names. On any other runtime, map them to the strongest, middle and cheapest models that runtime is configured with; on a single-model runtime every tier resolves to that one model, and "review one tier above" degrades to a fresh review pass by a separate agent or session — never the context that wrote the code. The labels themselves stay fixed: `pm-agent-batch` and the pipeline lint read them.

**Rules applied:** sonnet only on 2.2, 3.2 and 6.2 (XS/S, mechanical, with deterministic verifiers). Every other
milestone is opus, because it introduces a new pattern (`grep -rn "pacecheck\|NONLEXICAL\|GAPS\b\|stance" plugins/`
→ 0 hits on `main`) or shapes model behaviour. Reviews follow risk: the QA-gate and render-output rows get full opus
review; the doc-only 2.2 gets one sonnet pass.

### Resource Budget (verbatim)

```
max_parallel: 1                   # serial graph (see Waves)
token_budget: 6.0M                # HARD stop, not advice
heavy_verifiers: [kokoro-render+whisper-qa]   # 1.2, 3.1, 3.2, 4.1, 6.2 — run one at a time
```
calibration: default table, unmeasured here

_Arithmetic: implementation XS 60k + S 100k ×5 (1.1, 1.2, 3.2, 4.2, 6.2) + M 250k ×5 (2.1, 3.1, 4.1, 5.1, 6.1) =
1.81M; review 0.8× = 1.45M; heavy-verifier runs 5 × 150k = 0.75M; subtotal 4.01M × 1.5 ≈ 6.0M. Check the running total at every row flip (phase-gates
lesson)._

Run the graph as its orchestrator:

1. **Work wave by wave from the table.** For each milestone in the current wave, delegate to one sub-agent (your runtime's delegation capability) with that milestone's task prompt as its instructions. If the runtime lets you choose a model per sub-agent, use the row's Tier; if it does not, every row runs on the session's model — note that once in the table. Sub-agents work in this checkout and stage/commit **only paths inside their `Owns`**; use worktree isolation, where the runtime offers it, only when a row's `Owns` cannot be guaranteed disjoint. If the runtime cannot delegate at all, run the milestones yourself one at a time in wave order — every gate below still applies.
2. **Respect the cap.** Never more than `max_parallel` live sub-agents — queue the rest. Rows sharing a `heavy_verifiers` entry run one at a time.
3. **Validation gate before the next wave starts:** (a) run every milestone's declared verifiers yourself — never accept a sub-agent's claim that they passed; (b) spawn a review sub-agent at the row's Review tier with the diff and the instruction to *try to break it* (hostile fixtures, error paths, closure over request-scoped state, id/ordering assumptions), returning findings with severity; (c) if the wave had more than one milestone, run the phase-gates seam sweep; (d) append every DEVIATION to the deviations ledger. A wave with an open MEDIUM-or-worse finding does not unblock its dependents.
4. **Escalation:** a milestone whose verifiers fail twice at its tier re-runs one tier up; record `escalated_from: {tier}` in its Execution Graph row.
5. **Stop and surface to me** when the `token_budget` is exceeded, a `[Contract]` milestone fails review, or a DEVIATION changes a contract. Do not spend the remaining budget on dependents of a broken contract.
6. **Log every judgment call** under `## Execution decisions` in the decisions doc (the phase-gates Step 4 rule).
7. Optional, only if I have opted into multi-agent orchestration for this session **and** the runtime offers a scripted multi-agent orchestrator: the same table may instead be run as one script — a stage per milestone, the row's tier per stage, a review stage per item — with the harness enforcing the cap. The default is the wave-by-wave delegation above.

## Hazards & Verify-First List:

1. Verify before building on it:
   - **MP3 bytes are not reproducible across days:** `render.py:1980` writes `date` = today unless `--date` is given. Compare decoded PCM (`ffmpeg -i x.mp3 -f s16le - | md5sum`) for every "identical to 0.2.0" check.
   - **`TURN_GAP` is used in two places:** `estimate_seconds()` (`render.py:571`) and assembly (`render.py:1960`). Change one but not the other and the estimate drifts from the render; the 5% parity AC catches it.
   - **`--no-rotate` still writes rotation history:** `apply_rotation()` calls `record_rotation()` for fresh picks. Ear-test and fixture renders must set `PODCAST_STATE_DIR` to a scratch dir, or they skew the owner's real voice rotation.
   - **Rendering into an episode folder writes its `.tts-cache/cast.lock.json`.** For 1.2, render into a new subfolder and pin the original's voices explicitly with `--voices MAYA=…,ALEX=…` (read them from the original's lock), so the original's cache and lock stay untouched.
   - **The non-lexical mishearing map rests on ONE probe** ("hmm" → "him"). Extend it from the 1.2 and 4.1 real-whisper runs before trusting it, and keep the removal alignment-scoped so a real "him" still counts.
   - **The role heuristic is unproven.** It is a warning only; calibrate it in 6.1 and drop `SAME_TELLER` if its false-positive rate is > 20%.
   - Kokoro's rendering of "hmm"/"mm-hm"/"ha" is unknown. It is judged by the owner in 1.2, so don't tune QA around sounds the owner rejects.
2. Known gaps this phase can trip:
   - `SKILL.md` budgets "minutes × 153"; `render.py` uses `WPM = 158`. Stale until 3.2 (ledger L1).
   - `CLAUDE.md` points at `PLAN.md`, which doesn't exist (ledger L2). Work from the code and the phase docs.
   - `qa.py parse_script_lines()` already skips `[pause N]`. Any new directive must be skipped there too, as well as in `render.py parse_script()`.
   - `--dry-run` resolves the cast against kokoro's table, and must never import an engine. Keep pacecheck pure.
   - The CI privacy grep includes `docs/` and `test/`. Fixtures use fictional topics; baselines are numbers only.
3. Cannot run concurrently:
   - kokoro renders and whisper QA (CPU/GPU, and each episode's `.tts-cache`). One heavy run at a time (milestones 1.2, 3.1, 3.2, 4.1, 6.2).
   - `test/stranger.sh` with a shared `--reuse` state dir.

## Success Criteria:

- Follow the implementation plan exactly as documented
- Update progress tracking as we complete tasks
- Write clean, typed code that matches existing patterns in the codebase
- Every applicable Build Gate checklist item is satisfied (or explicitly re-marked N/A with reason) before the phase is considered done
- Every Phase Gate is honored: deviations ledgered as they occur, and zero open ledger rows + green hostile-env matrix before user testing

Let's pick up where we left off!
```

---

## Session Variations, Update Protocol & Tips

Generic across all phases — see the shared reference: `resume-howto.md` in the installed pm-agent skill
directory (wherever your agent loads its skills from). It covers session-start variations, update protocol,
tips and getting-help. Do NOT copy that content here.

---

## Key Documents Reference

| Document | Path | Purpose |
|----------|------|---------|
| Implementation Plan | `docs/phases/phase-human-touch/phase-human-touch-implementation-plan.md` | Living document with progress tracking |
| Decisions Log | `docs/phases/phase-human-touch/phase-human-touch-decisions.md` | All architectural decisions (canonical) |
| Requirements | `docs/phases/phase-human-touch/phase-human-touch-requirements.md` | Original PRD with full requirements |
| Task prompts | `docs/phases/phase-human-touch/phase-human-touch-task-<milestone>.md` | One per milestone, rules appended |
| Phase-gates addendum | `docs/ops/phase-gates-addendum.md` | Repo-specific gates and pre-deploy checks |
| Project Context | `CLAUDE.md` | Overall project architecture and principles |
| Session How-To | `resume-howto.md` beside the installed pm-agent skill | Generic variations, update protocol, tips |

---

## Emergency Recovery Prompt

```
The Phase Human Touch implementation plan seems out of sync. Please help me recover:

1. Read: docs/phases/phase-human-touch/phase-human-touch-implementation-plan.md
2. Scan the codebase to determine actual state, using these PHASE-SPECIFIC probes
   (run from plugins/podcast/skills/podcast):
   - 1.1: grep -n "Make it sound like people\|stances:" SKILL.md; grep -c "^## Reactions\|^## Stance" casts/two-host.md
   - 1.2: Progress Notes on row 1.2 record the owner's verdict? (the files live in the private twin, not this repo)
   - 2.1: grep -n "def pacecheck\|--strict" scripts/render.py; grep -n "NONLEXICAL" scripts/config.py
   - 2.2: grep -c "TBD-by-2.2" docs/phases/phase-human-touch/phase-human-touch-requirements.md (0 = done)
   - 3.1: grep -n "GAPS = \|def gap_for\|--pacing" scripts/render.py; grep -n default_pacing scripts/config.py ../../.claude-plugin/plugin.json
   - 3.2: grep -n "^WPM" scripts/render.py; grep -n "153" SKILL.md (0 hits = done)
   - 4.1: grep -n "NONLEXICAL\|strip_nonlexical" scripts/qa.py
   - 4.2: grep -c "^## Reactions\|^## Stance" casts/panel.md casts/solo.md
   - 5.1: grep -n default_level scripts/config.py; grep -c "^## Level notes" angles/*.md
   - 6.1: ls test/pacing/; grep -n pacecheck .github/workflows/validate.yml (repo root)
   - 6.2: grep -n '"version"' ../../.claude-plugin/plugin.json; grep -n version ../../../../.claude-plugin/marketplace.json
   - all: for s in config.py render.py qa.py rawfetch.py deliver.py audition.py; do python3 scripts/$s --selftest; done
3. Compare actual state vs plan
4. Propose how to update the plan to match reality
5. Identify what's actually complete vs incomplete
6. Suggest where to pick up from

Be thorough - this is critical for getting back on track.
```

---

## Completion Checklist

- [ ] All milestones marked "Complete"
- [ ] Progress Overview shows 11/11 complete (100%)
- [ ] All acceptance criteria met, each with EVIDENCE
- [ ] All six selftests, CI, `plugin validate --strict` ×2 and `test/stranger.sh` passing
- [ ] Documentation updated (README flags, SKILL.md, casts, angles)
- [ ] `CLAUDE.md` updated: eval suite path and Phase Human Touch status
- [ ] CHANGELOG.md has a Phase Human Touch entry (the repo has none today; create it or record N/A in the ledger)
- [ ] No active blockers; deviations ledger has 0 `open` rows
- [ ] Owner's release listen approved; readout recorded in the merge PR

Phase complete!

---

**End of Resume Prompt Document**
