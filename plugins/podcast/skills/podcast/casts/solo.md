# Cast: solo

**Use when** the listener wants the material without the conversation — a briefing to absorb at speed, or
simply a dislike of the two-host format.
**Pairs with** every angle, and it is the most efficient: no turn-taking overhead, so more content per minute.

## Voices

```cast
NARRATOR = af_bella, bm_george, am_echo @ 1.0
```

Three narrators in rotation — a warm American woman, an unhurried British man, a
deep American man. All three hold up over a long single-voice briefing.

Solo renders at the default `relaxed` pacing like every cast. For a news-style brief that should move fast, render
with `--pacing brisk` (the 0.2.0 timing: each line spoken whole, with the same short gap after every line).

## Opening

Vera names herself and lays out the shape of the briefing before starting, because there is no second voice to
mark the structure. The name is fixed across episodes.

> **NARRATOR:** I'm Vera. In the next twelve minutes: what <topic> actually is, the three numbers that matter,
> and the one thing most coverage gets wrong.

## NARRATOR — Vera, the briefer
One voice, direct address, second person where it helps ("you'll want to know…"). Structured out loud, because
there is no co-host to mark the transitions: name each section as it starts, and say what is coming next
before a hard turn. Precise about uncertainty — with no one to push back, the narrator does it themselves:
"the figure is widely quoted; the primary source is thinner than the coverage suggests."

## Roles

One voice, so Vera is both the teller and the listener's stand-in. She does the listener's part out loud instead of
inventing a second person. The two-host lesson moves in SKILL.md §4 change shape here:

- **One puzzle per segment** (plus the smaller question it may be parked behind). After the segment's one line of
  stakes, Vera puts the segment's puzzle to the listener as a question, once ("Wind pushes. So how does a boat sail
  toward it?"). It can put the listener in the decision ("You're the buyer. Which number do you check first?").
  Leave a beat with `[pause 1.2]` after it, the ladder's landing level, not a long silence. She may park it ("Keep
  that in mind. First, a smaller question."), and the segment ends by answering it.
- **No fake guesses.** There is no learner to guess, so Vera never guesses for the listener ("You're probably
  thinking…", "Most people would say…"). If `sources.md` records a common misconception, she names it as one,
  attributed ("The usual answer is the curved sail. It's only part of it."). Otherwise she goes straight to the
  answer.
- **A one-line recap instead of the explain-back.** Near the end of each segment, one line answers the puzzle in
  plain words ("So. The sail isn't only pushed. It's pulled."). Make it the segment's line to remember. It is a
  claim: it matches `sources.md` and never overstates ("all of it", "the only thing"). When words run short, keep
  the recap and cut a secondary fact.
- **Teaching still goes one idea at a time**: at most three sentences per idea, then a signpost or a short line
  before the next one.
- **Quotas that apply**, per segment (cold open and wrap exempt): the arc (stakes, setup, slow down, the turn in one
  short sentence, a landing pause, a reaction, a coda), one felt moment, one concrete image, the line to remember
  (the recap), at least one pause per ~90 s on the pause ladder, at most one sound, and about half the sentences
  six words or fewer. **What doesn't:** the educator/learner split, the guess before a reveal, the explain-back
  (the recap replaces it), the disagreement (see Stance) and the single-speaker word limit (pacecheck exempts a
  one-voice script).

## Reactions

One felt moment per segment, and it is **earned**: right after a verified line, never as the segment's first line.
In solo it is Vera's own, in the first person, reacting to the line she just said, never a story about her. No
"wow", no "that's incredible". Phrasings that render well:

- Surprise: "That's not what I'd have guessed." · "Forty-one. One customer." (repeat the number back)
- Unease: "That's a lot riding on one thing." · "Honestly, that one worries me a little."
- Landing it: "Okay. So here's what that means." · "Right. And that's the part that matters."

No "Wait." or "Hold on." as a reaction to her own line; with no one to interrupt, they read as acting. Holds (`...`
before the hard word) go on the turn, never inside a quote. At most one "hmm", "huh" or "ha" per segment, usually
none, and always in front of words; never "mm-hm" or "mhm" (the voice engine spells them out letter by letter).
Nothing demeaning and nothing stigmatising about health or identity.

## Stance

Solo has no `stances:` (the brief leaves it blank) and no disagreement to stage. Vera still has a point of view:

- After `[pause 2.5]`, she says what the facts mean to her, marked as opinion ("My read…", "I think…").
- Where the point is genuinely contested, she gives the strongest other view in a line or two, attributed to whoever
  holds it, then says why she lands where she does, or that she doesn't yet. Where an angle has the hosts argue each
  side (company-diligence's bull case and bear case), she gives each at full strength in turn, then her read.
- Where the facts are settled, no false balance: her read is a judgement call (what matters most, what to do, who
  it's for), not a dispute about the fact.
- Facts said on air are under **Verified** in `sources.md`; a "Reported, not re-verified" item is said as reported
  (attributed and hedged), and "Don't air" is never said. An opinion never carries any other fact.

## Writing this cast
- Signpost more than feels necessary. In a solo episode structure is the only navigation the listener gets.
- Vary sentence length hard. A single unvarying voice at an unvarying rhythm is what makes narration tiring.
- Keep the chapter headers meaningful — with one voice, chapter marks do the work the second host would.
- One puzzle per segment, plus the smaller question it may be parked behind (see Roles). No other rhetorical
  questions to fill the space where the co-host used to be; "But what does that mean? Well…" is an empty chair
  talking.
