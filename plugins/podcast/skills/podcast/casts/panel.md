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
below them, so the room reads her as the one in charge. Closes by saying where the evidence actually points, including "it doesn't point anywhere
yet" when that is the truth. Never splits the difference to be nice.

## ADVOCATE — Marcus, the case for
Argues the strongest real version of the position, the one its most serious proponents actually hold. Fast,
energetic, concrete — reaches for the specific number or example rather than the principle. Concedes a point
when it is well made; an advocate who never concedes is a strawman with a microphone.

## SKEPTIC — Nora, the case against
Argues the strongest real objection. Dry, precise, unhurried. Attacks the evidence rather than the motive:
what the study actually measured, what the number leaves out, what would have to be true. Says plainly when
the other side has the better of an exchange.

## Writing this cast
- Use their names in dialogue. Three voices addressing each other as "you" is hard to follow; "Nora, that
  assumes the benchmark is representative" is not.
- **Both sides must be positions someone actually holds**, sourced and verified. Invented opposition is the
  failure mode of this format — it produces two views that are secretly the same, or a strawman getting
  knocked over.
- Let them interrupt and answer each other directly, not through the host. Alternating monologues is a panel
  in name only.
- The host speaks least. If the moderator has the most words, the debate isn't happening.
- Landing on a conclusion is fine and often right. Reaching it by having one side quietly stop arguing is not.
