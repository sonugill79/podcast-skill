---
name: podcast
description: Research any topic and turn it into a verified, two-host, podcast-style audio episode generated on this machine. Parallel research agents gather sources, the load-bearing claims are re-checked against primary sources, a script is written for the ear, local text-to-speech renders it, and a transcription round-trip catches dropped or garbled audio. Four angles are available, interview-prep (a company and role before an interview), learn-topic (understand any subject), company-diligence (a company as investor, partner or competitor) and product-research (evaluate a tool before buying or adopting). Works with nothing installed by writing the script; voices and audio QA are optional upgrades the user asks for by name. Use when someone asks for a podcast, an audio briefing or deep-dive, something to listen to, or interview prep, company research or a product evaluation as audio.
---

# Podcast: topic → verified research → two-host script → audio

`SCRIPTS` below means the `scripts/` directory next to this file. When running inside a plugin that is
`${CLAUDE_PLUGIN_ROOT}/skills/podcast/scripts`. Angle playbooks are in `angles/`, casts in `casts/`, starter files
in `templates/`. An **angle** decides what the episode covers; a **cast** decides who covers it.

Always call the scripts with plain `python3` / `bash` as written here. They find their own runtime: anything needing
installed packages re-executes itself inside the managed environment. If a script exits **3**, nothing is installed for
that step — relay its one-line message to the user as an offer, and carry on with the rest of the episode.

## Step 0 — fix what's missing yourself, in the background

Run `bash SCRIPTS/setup.sh status`.

**Everything present** — one line saying so, then start the episode.

**Audio works, but on the thinner engine** — `status --json` has `voice_downgraded: true`, or the voice row names
piper while kokoro is absent. This is a plugin-0.1.2 install that auto-fetched piper before kokoro became the default
under `auto`; it renders, it just sounds worse. Treat it like anything else in step 0: `autosetup` already plans it as
an *upgrade* (`auto_setup.upgrades`, not `auto_setup.missing`), so launch it in the background, say in one line that
the better voice is downloading and that this episode may still be in the old one, and get on with the research.
**Never delay an episode for it** — piper renders now, and because `auto` resolves to the best *installed* engine at
render time, the next render picks kokoro up by itself. Someone who set `voice_engine: piper` on purpose is left
alone, and so is `auto_setup: never`.

**Something missing** — the user asked for an episode, not a shopping list. Unless `auto_setup` is `never`:

1. Launch `bash SCRIPTS/setup.sh autosetup` **in the background, immediately**. It installs what's missing in
   priority order (ffmpeg, then the voice engine, then the QA model) with no sudo and nothing outside the plugin's
   own folder.
2. **Tell them once, in one line, what is being fetched and how big.** Read that line from the top of
   `<state>/autosetup.log` — **never pipe `autosetup` into `head` or anything else**, because a closed pipe kills the
   install (a real defect found in review, 2026-09-12). Do not ask permission; do say what is happening, and mention
   that `auto_setup=never` turns it off.
3. **Start the research in the same breath.** The download and the research run together; downloads finish in under a
   minute, research takes minutes, so the audio is normally ready before the script is.

**Before rendering**, read `<state>/autosetup-result.json`. It reports each component separately, so render as soon
as ffmpeg and the voice are done — never wait on the audio checker, which is much larger and only needed afterwards.
`state: running` with those two still pending → wait, and say so. A component failed → use what succeeded and state
plainly what didn't. All failed → deliver the script, quote the one-line reason, and if it needs something only they
can do (an unsupported platform), give the exact command.

Never block the episode on a download, never re-run research because a download was slow, and never install anything
when `auto_setup` is `never`.

These phrases still work if someone wants to drive it manually:

| The user says | Do this |
|---|---|
| `upgrade audio` | `bash SCRIPTS/setup.sh install audio` — ffmpeg plus the kokoro voice |
| `upgrade voice` | `bash SCRIPTS/setup.sh install voice-kokoro` (~521 MB, best quality — the default) or `voice-piper` (~375 MB, faster, noticeably thinner) |
| `upgrade qa` | `bash SCRIPTS/setup.sh install qa-base` (~575 MB); `qa-small` and `qa-medium` are larger and more accurate |
| `stop installing things` | `python3 SCRIPTS/config.py set auto_setup=never` |
| `configure telegram` | Needs `~/.config/telegram-send/bots.json`; then `python3 SCRIPTS/config.py set telegram_bot=<name>` |
| `status`, "what do I have" | `bash SCRIPTS/setup.sh status` |
| something is broken | `bash SCRIPTS/setup.sh doctor` |

After any install, **continue where you left off** — if a script exists, render it; never redo research.

## Invocation

`/podcast <topic> [--angle interview-prep|learn-topic|company-diligence|product-research|debate] [--cast two-host|panel|solo] [--minutes N] [--depth quick|standard|deep] [--personal] [--no-deliver]`

- **Angle:** infer it ("interviewing at X" → interview-prep, "should we use X" → product-research, "X as an
  investment" → company-diligence, a yes/no or either-or question with real disagreement behind it → debate,
  otherwise learn-topic). Ask only if genuinely ambiguous.
- **Cast:** read `casts/README.md`, then pick one and hold it for the whole episode. The default comes from
  `config.py status --json` → `config.default_cast` (`two-host` unless the user changed it);
  `debate` requires `panel`; `solo` when the listener wants a briefing rather than a conversation. **One cast per
  episode, start to finish** — a listener is still learning the voices, and swapping mid-episode loses them.
  Across episodes, including inside a series, the cast is free to change.
- **Depth:** quick = 3 research agents, ~8 verified claims, ~10 min. standard (default) = 5 agents, ~20 claims,
  ~20 min. deep = standard plus an adversarial reviewer, ~25 min.
- **`--personal`:** only with this flag may you read the user's mail or calendar, only for this episode, and record
  that you did in the brief.

**Cost:** research, verification and the script spend model tokens; audio and QA are free and local. One request =
one episode. Never batch topics or schedule episodes without being asked.

## 1. Brief
Episodes live in the configured folder (`python3 SCRIPTS/config.py status --json` → `config.episodes_dir`), one directory per
episode named `<topic-slug>-<yyyy-mm>`. Write `brief.md`: topic, angle, depth, minutes, date, the listener's goal, and
whether any personal sources were used. If a listener profile is configured, read it and write for that person by
name; otherwise write for a general audience.

## 2. Research
Read `angles/<angle>.md` for the research areas, then launch **all agents in one message** (model: sonnet), one per
area, each writing `research/0N-<area>.md`. For `debate`, the two side-agents are launched **blind to each other**:
each is told to build its own side as strongly as it honestly can, and they are merged only at the script stage. An
agent asked to argue both sides converges into mush. Require of every agent: a source URL and a tag (`[primary]`,
`[secondary]`, `[snippet]`) on each claim, a "conflicts and couldn't verify" section, no logins or paywall
circumvention, and a date on every figure.

## 3. Verify — do this yourself, never delegate
This is what makes an episode trustworthy.
1. List the load-bearing claims: every number, date, name and quote the script will say, plus the angle's must-verify list.
2. Check each against a primary source. For anything quoted verbatim use
   `python3 SCRIPTS/rawfetch.py <url> --grep "exact phrase"` (0 = found, 1 = not found, 2 = fetch error). Summarising
   fetch tools paraphrase; a quote that isn't on the page is the failure this step exists to catch.
3. Check what each quote was *about* before repeating the researcher's framing.
4. Flag numbers that are true but misleading (one-off items inflating a profit, a placeholder in a structured field).
5. Resolve disagreements between research files yourself; if unresolved, say so on air.
Write `sources.md` with: **Verified** (claim + source), **Reported, not re-verified**, **Don't air**, and anything to
re-check before a deadline.

## 4. Script
`script.txt`: speaker lines, `---` for a segment break, `[pause N]` for silence, `#` comments, and chapter headers
like `# ── 3. The bit about money ─────` which become chapter markers **inside the MP3**.
- **Speaker labels are the chosen cast's, exactly** — `MAYA:`/`ALEX:` for two-host, `HOST:`/`ADVOCATE:`/`SKEPTIC:`
  for panel, `NARRATOR:` for solo. A label the cast doesn't declare fails the render with its line number.
- Read the cast file and write each speaker as the person it describes — vocabulary, sentence length, what they
  push on, who concedes. The voices differ, but the writing is what a listener hears as personality.
- Follow the angle's segment outline. Budget **minutes × 153 words**.
- **Chapter headers earn their keep now that players show them.** One per segment, named for what is in it
  ("What the filings actually say"), not "Segment 3".
- Write for the ear: short sentences, one idea per line, numbers spelled out ("four hundred ninety-five million"),
  "quote" before verbatim text with attribution, hosts who clarify and disagree.
- Say plainly what could not be verified. Label allegations and anonymous claims as such.
- Keep correct spellings. Pronunciation fixes live in `lexicon.txt` **in the episode's own folder** (seed it from
  `templates/lexicon.txt` when you first need one); `qa-ignore.txt` sits beside it. The scripts look there by default.
- Check the length before rendering: `python3 SCRIPTS/render.py <script> --dry-run`.

## 5. Render
`python3 SCRIPTS/render.py <script> <out.mp3> --cast casts/<cast>.md --title "<episode title>" --album "<show>"`
— pass the same cast the script was written for. Title, artist, date, genre and the chapter marks are written into
the MP3, so it arrives in a podcast app as an episode rather than an untitled blob; `--cover <image>` embeds
artwork. Per-speaker pace comes from the cast file, `--speeds SPEAKER=1.05` overrides one, `--speed` sets the
baseline. For a full episode run it in the background **only in an interactive
session**. In a non-interactive run (`claude -p`) the session can end before a backgrounded render finishes, leaving no
audio; render in the foreground there. Exit **3** means no voice
engine is installed: tell the user the script is ready and offer `upgrade voice`. Rendering is cached per line, so
fixing a few lines re-renders only those.

## 6. QA
`python3 SCRIPTS/qa.py <script> <out.mp3>` compares the audio against the script and fails on: DROPPED or TRUNCATED
lines, MISSING runs of 4+ words, EXTRA AUDIO (repeats, wrong-line audio), misheard NAMES, lost or added NEGATIONS, or
coverage below 0.96. Exit 3 means QA isn't installed — offer `upgrade qa`.
- Structural failures mean **re-render**, never an ignore rule.
- For a NAMES flag, render the word alone and transcribe it: if the voice is wrong add a `lexicon.txt` rule and
  re-render; if only the transcriber is wrong add a `qa-ignore.txt` pair.
- Numbers are not QA'd (the script spells them, the transcriber writes digits) — check numeric lines against `sources.md`.

## 7. Deliver and close
Tell the user where the file is. If `telegram_bot` is configured, `python3 SCRIPTS/deliver.py <out.mp3> --bot <name>`
sends it behind a privacy gate that refuses any chat beyond the owner and the bot (exit 3). Never pass
`--allow-shared` unless explicitly asked. Chapter times come from the generated `chapters.json` — never estimate them.
Finish by appending an outcome to `brief.md`: length, QA coverage, and anything learned.

## Failure modes already seen

| Symptom | Cause | Fix |
|---|---|---|
| A quote isn't on the page | a summarising fetch paraphrased it | `rawfetch.py --grep` |
| Salary or price reads like a placeholder | structured job/product data is often boilerplate | take it from the page text |
| A transcript "confirms" a phrase spanning two list items | text joined across block boundaries | already guarded; re-check with `--grep` |
| Voice mangles a name | pronunciation | `lexicon.txt` rule, then re-render |
| Transcriber misspells a name the voice said correctly | transcription quirk | `qa-ignore.txt` pair |
| Chapter times wrong | estimated by hand | use `chapters.json` |
| Research files contradict each other | different source vintages | verify yourself; air the hedged version |
