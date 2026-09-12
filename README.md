# podcast — turn any topic into a verified audio episode

A [Claude Code](https://claude.com/claude-code) plugin. Give it a topic; it researches the topic with parallel agents,
**re-checks the load-bearing claims against primary sources**, writes a two-host script, renders it to audio on your
machine, and verifies the audio actually matches the script.

Nothing is sent anywhere. Research uses ordinary web requests; the voice and the transcription both run locally.

## Install

```
/plugin marketplace add sonugill79/podcast-skill
/plugin install podcast@podcast-skill
```

You'll be asked a few questions (where to save episodes, which voice, optional Telegram). Change them any time with
`/plugin configure podcast@podcast-skill`.

**Prefer to just ask?** Paste this to Claude and it will do the install for you:

> Please install the podcast plugin for me. Add the marketplace `sonugill79/podcast-skill`, then install
> `podcast@podcast-skill`. Set `episodes_dir` to `~/podcast-episodes` and leave the rest at their defaults. Show me
> the result of `claude plugin list` when you're done, and remind me to restart my session.

Claude will ask permission the first time it runs each command. Both routes do exactly the same thing — the slash
commands above are the built-in path, the prompt is a convenience.

**Restart your session after installing.** Skills are loaded when a session starts, so `/podcast` won't exist in the
session you installed from — quit, start Claude again, and it's there.

Then:

```
/podcast how container shipping pricing works
/podcast Acme Corp --angle interview-prep
/podcast Postgres vs SQLite for my side project --angle product-research --depth quick
```

## It works before you install anything

The first run tells you what's available and what isn't. With nothing installed you still get the researched,
source-checked **script**. Audio and QA are upgrades you ask for by name, and each one tells you its size first:

| | Ships as | Say this to upgrade | Size |
|---|---|---|---|
| **Voice** | none — script only | `upgrade voice` | Piper ≈375 MB on disk; Kokoro adds its 338 MB model for better voices |
| **Audio QA** | skipped | `upgrade qa` | ≈575 MB for the base level (most of it the transcription runtime); small and medium are larger |
| **Delivery** | file on disk | `configure telegram` | — |

Upgrades continue where you were: if the script is already written, it just renders.

Other things you can say: `status`, `doctor` (when something looks wrong).

## Angles

| Angle | Use it for | Ends with |
|---|---|---|
| `learn-topic` (default) | understanding a subject | how it applies to you, resources, one thing to try |
| `interview-prep` | a company and role before an interview | questions to ask, things to weigh |
| `company-diligence` | a company as investor, partner or competitor | bull vs bear case, what to watch |
| `product-research` | deciding whether to buy or adopt something | buy / try / skip, and what would change it |

Depths: `quick` (~10 min, 3 research agents), `standard` (~20 min, 5 agents), `deep` (adds a reviewer that tries to
disprove the script).

## What it costs

The research, verification and writing use your Claude usage — roughly three to five sub-agents per episode. Audio
and QA cost nothing after the one-time download. One request produces one episode; it never runs on a schedule.

## Requirements

- Python 3.9+ (standard library only for everything except the voice engine)
- `ffmpeg` for audio — the installer prints the command for your system rather than installing it for you
- Disk: nothing until you upgrade; ≈375 MB for voices, ≈575 MB for audio QA, ≈1.2 GB with everything installed
  (measured on Linux, 2026-09-12). Installs take well under a minute each on a decent connection.
- Some voice engines need `espeak-ng`; again, you'll be told

## Why it re-checks its own research

Every episode is built from a `sources.md` that separates **verified** claims from reported ones, and lists what was
deliberately left out. In testing this caught a profit figure inflated by a one-off tax item, a quote attached to the
wrong subject, a job posting whose structured salary field was placeholder data, a sensor feed that had silently
stopped reporting, and a page that never said what a summary claimed it said. The verification step is the point.

## Third-party components

Voice and transcription models are downloaded from their own projects on first upgrade; their licences are their own —
see [Piper](https://github.com/rhasspy/piper), [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) and
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) before redistributing anything.

## Licence

MIT — see [LICENSE](LICENSE).
