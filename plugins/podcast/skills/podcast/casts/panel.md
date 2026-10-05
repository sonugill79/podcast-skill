# Cast: panel

**Use when** the topic has real, live disagreement and the listener deserves both cases at full strength
rather than one summary that splits the difference.
**Pairs with** `debate` above all; also `product-research` and `company-diligence` when the decision is
genuinely contested.

## Voices

```cast
HOST     = bf_lily, af_aoede, bm_george   @ 0.98
ADVOCATE = am_adam, am_fenrir, bf_isabella @ 1.03
SKEPTIC  = af_kore, af_alloy, am_echo     @ 1.0
```

Each slot lists three interchangeable voices and the renderer rotates between them,
so a weekly series doesn't sound identical every time. The first is the default and
what `--no-rotate` picks. A choice is pinned in the episode's cache, so re-rendering
after a script fix keeps the same voices.

Three deliberately unmistakable voices: a British woman at 187 Hz, an American man at 117 Hz, an American
woman at 148 Hz. A listener can tell who is speaking before the second word, which is what makes a three-way
exchange followable in audio.

Chosen against measurement, not vibes (see `VOICES.md`): the two women are separated by 39 Hz **and** an
accent, and the skeptic's voice is naturally the slowest of the three, so the dry temperament costs almost no
artificial slowing. An earlier draft used `af_nicole` here, which measures at 120 wpm against a 187 wpm median
— a soft, slow delivery that is lovely for a sleep story and wrong for an argument.

## Names

The speaker labels are roles, so scripts and QA stay stable; the people have names, and **the names never
change between episodes**. A listener who comes back should meet the same three people.

| Label | Name | Voice |
|---|---|---|
| `HOST` | **Iris** | British woman, measured |
| `ADVOCATE` | **Marcus** | American man, quick |
| `SKEPTIC` | **Nora** | American woman, dry |

## Opening

Every episode opens with Iris introducing herself, the question, and both guests **by name and by the position
they are taking** — so a listener knows who is who before the first argument starts, and can follow the rest by
voice alone. Roughly:

> **IRIS:** I'm Iris, and today we're asking <the question>. Making the case for <A> is Marcus. Arguing the
> other side is Nora. My job is to keep them both honest, and to tell you at the end where the evidence
> actually points.
> **MARCUS:** Happy to be here. I think this one is clearer than people admit.
> **NORA:** And I think Marcus is about to overstate it.

Keep it under about twenty seconds. Each guest gets one line that previews their stance and their temperament
— not a summary of their argument, which is what the next segments are for.

## HOST — Iris, the moderator
Neither side's friend. Opens with the question and why it is live now, hands out the floor, and — the part
that matters — presses whichever side just overreached. Pitched a touch under the others and paced a touch
below them, so the room reads her as the one in charge. While a guest makes their case she mostly listens (see
Roles). Closes by saying where the evidence actually points, including "it doesn't point anywhere
yet" when that is the truth. Never splits the difference to be nice.

## ADVOCATE — Marcus, the case for
Argues the strongest real version of the position, the one its most serious proponents actually hold. Fast,
energetic, concrete — reaches for the specific number or example rather than the principle. Concedes a point
when it is well made; an advocate who never concedes is a strawman with a microphone.

## SKEPTIC — Nora, the case against
Argues the strongest real objection. Dry, precise, unhurried. Attacks the evidence rather than the motive:
what the study actually measured, what the number leaves out, what would have to be true. Says plainly when
the other side has the better of an exchange.

## Roles

A panel has **no learner**. Marcus and Nora are the experts on their own side, and Iris is a sharp listener, not a
novice. So the two-host lesson moves in SKILL.md §4 (the guess before a reveal, the explain-back, "the learner never
supplies a fact") do not apply here. Any of the three may state a fact, and a position is attributed to the people
who hold it. Facts said on air are under **Verified** in `sources.md`; a "Reported, not re-verified" item is said as
reported (attributed and hedged), and "Don't air" is never said. This is the panel's version:

- **The guests tell; Iris usually listens.** In each argument segment one guest tells, and the next segment the
  other does. On `debate`, Marcus tells segment 3 and Nora segment 4, each **uninterrupted**: the other guest stays
  out until cross-examination, with no rebuttal and no aside. Iris still comes in every few lines with a reaction or
  a clarifying question, so the case is heard as a conversation, not a speech, and no run passes about ninety words
  (pacecheck's `LONG_RUN`). On other angles, follow the angle's outline: in its argument segments alternate which
  guest tells and let the other answer in a line or two before the segment ends. The verdict or wrap segment is
  always Iris's, on any angle; a partisan never delivers it.
- **Iris listens out loud.** Her one-to-five-word reaction is how the audience knows a point just landed. She asks
  what the audience is asking ("Marcus, what did that survey actually count?"). Once per guest's case she restates
  it as a question for that guest to confirm or correct ("So your case rests on the renewal rate?"). She never
  states a side's case in her own words and leaves it standing, and she never argues one.
- **Iris tells her own segments**: the question, the common ground, pressing the weak links, where the disagreement
  lives, where the evidence points (debate segments 1, 2, 6, 7 and 8). In the common ground she asks each guest to
  confirm the floor ("Nora, you'd accept that number?" "I would. It isn't in dispute.").
- **When a case rests on a mechanism**, the guest telling it teaches it: one idea per turn, at most three sentences,
  and Iris asks the next natural question. The segment ends by answering the question it opened with.
- **Arc, pauses and sounds are the same as every cast** (SKILL.md §4): the per-segment arc, one felt moment, one
  concrete image, the line to remember, the pause ladder, at least one pause per ~90 s, and the sound rules.
  Debate segment 1 is the cold open and segment 8 the wrap; both are exempt from the per-segment quotas.
  `[pause 2.5]` before switching to opinions falls before Iris's verdict. Thinking beats and holds go mostly on
  Iris's questions and on a guest working toward a concession, never inside a quote.

## Reactions

One felt moment per segment, and it is **earned**: right after a verified line, never as the segment's first line.
On a panel it is usually Iris's reaction or a guest's honest concession. No "wow", no "that's incredible", and no
heat performed for the room. They disagree about the question, never about each other. Phrasings that render well:

- Iris, pressing: "Hold on. [pause 0.7] Marcus, is that the same study?" · "Nora. That's a big claim. Where is it
  from?" · "Okay. So that's the number you both accept."
- Surprise or unease, from Iris: "Wait. One customer?" · "That's a lot riding on one survey."
- A guest conceding: "Fair. That's the weak part of my case." · "Okay. I'll grant you that one." · "Right. The sample
  is small. Here's why I still think it matters."
- A guest repeating a number back in cross-examination: "Forty-one percent. Of one region."

Words carry it. At most one "hmm", "uh-huh", "huh" or "ha" per segment, always in front of words, never a line on
its own; never "mm-hm" or "mhm" (the voice engine spells them out letter by letter). Nothing demeaning and nothing
stigmatising about health or identity; no guest scores off a person. No invented experience: Marcus and Nora argue
from sources, never from a story about themselves.

## Stance

The stances are **the sides that already exist**, found by the research, never invented (SKILL.md §3). In
`brief.md`:

```
stances:
  ADVOCATE: <the position, as its most credible proponents hold it>
  SKEPTIC: <the strongest real objection>
  HOST: none; presses whichever side overreaches
```

- **Proposition** question: Marcus argues for, Nora against.
- **Versus** question: Marcus champions option A and Nora option B. Each makes the honest case against the other
  option, as that option's critics actually make it, never a caricature (`angles/debate.md`).
- Off `debate` (a contested `product-research` or `company-diligence`), the sides are the decision: adopt it or
  don't, the bull case or the bear case.
- Iris has no stance. Her verdict is where the evidence points, and that can be "nowhere yet". She never smuggles
  in a third position.
- The guests mark what a fact means as opinion ("My read…", "I think…", "Honestly…") and keep facts as facts with a
  source. Facts said on air are under **Verified** in `sources.md`; a "Reported, not re-verified" item is said as
  reported (attributed and hedged), and "Don't air" is never said. A conclusion is fine; one side quietly dropping
  its case is not one.

## Writing this cast
- Use their names in dialogue, in short sentences. Three voices saying "you" to each other is hard to follow; a
  name at the start of the turn tells the listener who is being answered:

  > **SKEPTIC:** Marcus. That benchmark ran on one codebase. One. Would you bet a team on it?
  > **ADVOCATE:** Fair, Nora. It's one codebase. My read is it's still the best evidence anyone has.

- **Both sides must be positions someone actually holds**, sourced and verified. Invented opposition is the
  failure mode of this format — it produces two views that are secretly the same, or a strawman getting
  knocked over.
- In cross-examination, let them answer each other directly, not through the host. Alternating monologues is a
  panel in name only.
- The host speaks least. If the moderator has the most words, the debate isn't happening.
- Landing on a conclusion is fine and often right. Reaching it by having one side quietly stop arguing is not.
