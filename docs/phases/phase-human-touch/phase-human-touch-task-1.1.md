# Task Prompt — Phase Human Touch, Milestone 1.1

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
- [ ] Every PRD Script Rules row appears in §4. CHECK: a reviewer ticks the rows one by one. EXPECT: 10/10. EVIDENCE: pending
- [ ] No existing §4 rule removed. CHECK: `git diff -U0 main -- SKILL.md | grep '^-[^-]'` lists only replaced cast-rhythm lines. EXPECT: no honesty/quote/spelling/budget/sources lines removed. EVIDENCE: pending
- [ ] `two-host.md` voices block and Opening unchanged. CHECK: `python3 scripts/render.py --selftest` + `git diff main -- casts/two-host.md`. EXPECT: selftest OK, no change inside the ```cast block. EVIDENCE: pending
- [ ] Privacy grep clean (CI pattern). EVIDENCE: pending
- [ ] Universal Clauses + Cross-Cutting Rules (below) satisfied

**Testing Strategy:**
- **Unit Tests:** `render.py --selftest` (the cast still parses).
- **Integration Tests:** none (prose).
- **Manual Verification:** read §4 top to bottom as the model would, checking that no rule contradicts another (e.g. "short lines" against "one idea per line" — keep both).
- **Declared Verifiers:** CI `validate.yml` (selftests, manifests, privacy grep).

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
