# Casts

A cast is who is talking, how they talk, and which voice each one is bound to. Angles decide *what* an episode
covers; casts decide *who covers it*. One cast per episode, start to finish — see "Choosing a cast" below.

## The one machine-readable part

Every cast file carries a fenced ```cast block that `render.py --cast <file>` reads:

```
SPEAKER = voice [@ speed]
```

`SPEAKER` must match the speaker labels in the script exactly. `voice` is a voice id the engine knows.
`@ speed` is optional pacing (0.5–2.0; a cast should stay within about 0.95–1.08 — more than that reads as a
defect, not a personality). Everything else in the file is prose for whoever writes the script.

## What a cast can and cannot change

Kokoro has no emotion or prosody control — there is no "excited" setting. A cast changes three things:

1. **Voice** — 54 are available in the shipped pack (11 American female, 9 American male, 4 British female,
   4 British male, plus Spanish, French, Hindi, Italian, Japanese, Portuguese and Mandarin).
2. **Pace** — a few percent either way, per speaker.
3. **The writing** — sentence length, vocabulary, hedging, interruptions, what excites them, verbal tics.

The third one carries most of the perceived personality, and it is the reason a cast file is mostly prose.
Write the persona sections as instructions to the script writer, not as decoration.

## Choosing a cast

- **One cast per episode.** Mixing casts inside an episode is confusing — a listener is still learning the
  voices. Pick before writing the script and stay with it.
- **Across episodes, mix freely.** A series may hold one cast for continuity or change it per topic; that is
  the listener's call, not a constraint of the format.
- **Match the cast to the angle.** A flippant cast on top of `company-diligence` produces something nobody
  would forward to an investor. Each cast lists the angles it suits.

## When no shipped cast fits

The three casts cover most episodes, but the voice a topic wants is sometimes not one of them — a sleep story
wants the soft, slow voice that would ruin a debate; a documentary wants 87 Hz gravitas. **`VOICES.md` is the
reference for that**: all 54 voices with measured pitch, pace and level, and a "picking for a job" table.

Override without leaving the cast: keep its speaker labels and swap the voice.

```bash
python3 SCRIPTS/render.py script.txt out.mp3 --cast casts/solo.md --voices NARRATOR=af_nicole
```

Write a new cast file only when the *roles* change, not when only the voices do.

## Writing a new cast

- **Make the voices unmistakable.** Listeners identify a speaker in the first syllable or they lose the thread.
  Vary accent and register, not just name — two American male voices in one episode is the classic mistake.
- **Give each speaker a job**, not just a temperament: who opens, who presses, who concedes, who closes.
- **Keep the roster small.** Three distinct voices is a panel; five is a crowd nobody can follow in audio.
- **Personality never licenses sloppiness.** A contrarian host still cites verified sources. The rules in
  `SKILL.md` apply to every cast equally.
