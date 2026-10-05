# Angle: learn-topic

**Use when** the listener wants to understand a subject: a technology, a concept, a field, a historical event, a
scientific question.
**Listener goal:** come away with a correct mental model, the current state of play, what's genuinely contested, how it
touches their world, and where to go deeper.

## Brief (ask only if missing)
- The topic. The starting level is `--level` (`brief.md` `level:`): new to it = `intro`, knows the basics =
  `informed` (the default: a smart generalist with a technical background), practitioner wanting the frontier =
  `expert`. Ask only if the request says neither and the config default plainly doesn't fit.
- Why now: a decision, a project, or curiosity. This shapes the "how it touches your world" segment.

## Research areas (one agent each)
| # | Area | Focus |
|---|---|---|
| 1 | Fundamentals & mental model | Precise definitions from authoritative sources, how it works step by step, the best existing analogies and **where each analogy breaks** |
| 2 | History & key moments | Origin, the 3–5 turning points with dates, the people involved (attributions verified) |
| 3 | Current state & frontier (last 12–24 months) | Latest developments, adoption numbers with dates, leading players/labs/projects, what changed recently |
| 4 | Debates, misconceptions & open questions | Steelman each side of real disagreements, common misconceptions with corrections, what's unknown. Distinguish settled from contested |
| 5 | Practice & going deeper | How it applies to the listener's projects/work (use `listener.md`), tools to try (prefer free/local), 3–5 resources (books, papers, courses, talks), **each verified to exist** |

`quick` depth merges 1+2 and 3+4, and keeps 5 (3 agents).

## Segment outline (≈ share of runtime)
1. Hook: why this matters now, in one concrete example (5%)
2. The one-sentence version, then what that sentence hides (7%)
3. Building the mental model: analogy first, then precision, then where the analogy breaks (22%)
4. History in two minutes: the turning points (10%)
5. Where it is now: the frontier, with numbers and dates (16%)
6. What people get wrong, and what's genuinely contested (15%)
7. How it touches your world: the listener's work and projects (12%)
8. How to go deeper: three resources and one thing to try this week (8%)
9. Wrap: three things to remember, what couldn't be verified (5%)

## Level notes
`brief.md` `level:` sets the pitch (SKILL.md §Invocation).

| Level | Assumes | Explain or add | Skip or shorten |
|---|---|---|---|
| intro | everyday knowledge only | Every term in plain words the first time it is said; one image per concept, and where it breaks; each segment's line to remember (SKILL.md §4) is a one-sentence recap. The puzzle is the everyday one ("Why does…?") | The frontier (segment 5) shrinks to the one development that matters; history keeps only the turning points the model needs; no names or jargon the listener won't use again |
| informed (default) | the basics; a technical generalist | New or contested terms only | Nothing: the outline as written |
| expert | the field's vocabulary and textbook model | The precise mechanism and its limits, current numbers, the open questions and where experts disagree, in detail. The puzzle is an edge case; the wrong guess is a practitioner's misconception | Segments 2–4 compress to a framing ("you know the textbook version; here's where it breaks"). No definitions of standard terms, no analogy-first build |

Level never changes verification: the must-verify list below, SKILL.md §3 and `sources.md` tracing are the same at every level, and so is saying what couldn't be verified. Where SKILL.md §4's lesson shape applies, it holds at every level: the level changes what the learner's puzzle and wrong guess are, never whether the guess comes from `sources.md`.

## Must verify yourself
- Definitions and any "X is Y" claim the model is built on.
- Dates, statistics, "first/largest/fastest" claims.
- Quote attributions (misattribution is the most common error in this angle).
- **Every named resource exists**: title, author, year, and a working URL (`rawfetch.py --grep` the title).

## Don'ts
- No false balance on settled questions. Say plainly which side the evidence supports.
- No invented examples presented as real. Label hypotheticals as hypothetical.
- Don't pad with history if the listener asked about the frontier. Rebalance the outline to their level (Level notes above).
