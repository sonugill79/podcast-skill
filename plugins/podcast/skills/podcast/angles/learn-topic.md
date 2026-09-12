# Angle: learn-topic

**Use when** the listener wants to understand a subject: a technology, a concept, a field, a historical event, a
scientific question.
**Listener goal:** come away with a correct mental model, the current state of play, what's genuinely contested, how it
touches their world, and where to go deeper.

## Brief (ask only if missing)
- The topic, and the starting level (new to it / knows the basics / practitioner wanting the frontier). Default: smart
  generalist, technical background.
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

## Must verify yourself
- Definitions and any "X is Y" claim the model is built on.
- Dates, statistics, "first/largest/fastest" claims.
- Quote attributions (misattribution is the most common error in this angle).
- **Every named resource exists**: title, author, year, and a working URL (`rawfetch.py --grep` the title).

## Don'ts
- No false balance on settled questions. Say plainly which side the evidence supports.
- No invented examples presented as real. Label hypotheticals as hypothetical.
- Don't pad with history if the listener asked about the frontier. Rebalance the outline to their level.
