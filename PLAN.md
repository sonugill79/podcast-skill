# podcast-skill — implementation plan

**Goal:** package the working `/podcast` pipeline (currently welded to one machine) as a Claude Code plugin that a
stranger can install and use immediately, with heavier capability arriving as *named upgrades* they ask for.

**Status:** **v0.1 shipped 2026-09-12** to the private repo `sonugill79/podcast-skill` (commit `dfbe00c`).
Privacy gate passed; stranger test passes end to end. **Still private** — going public is a separate decision the
owner makes after real use (see section 5, item 10).

---

## 1. Decisions already made (don't re-litigate)

| Decision | Choice | Why |
|---|---|---|
| Distribution | Claude Code **plugin** in its own repo that is also a marketplace | Repo doubles as marketplace; `/plugin install` handles updates |
| Repo visibility | **Private first**, public only after the gate in section 6 | Source project contains job-search material |
| First-run behaviour | Works with **nothing installed** (writes the script), prints active tiers + how to upgrade | Nobody waits for a 3 GB download on first use |
| Upgrades | User says `upgrade voice` / `upgrade qa` / `configure telegram` in natural language | Owner's requirement: flexible, seamless, discoverable |
| Voice engines | `piper` (small) and `kokoro` (best); `kokoro-torch` still supported if present | Owner wants flexibility and an upgrade path |
| QA | faster-whisper (pip) or whisper.cpp if the user already has it; levels base/small/medium | Avoids making users compile whisper.cpp |
| Delivery | Local file by default; Telegram optional | Telegram config is owner-specific |
| Licence | MIT (at publication) | — |

## 2. Verified platform mechanics (checked against Claude Code 2.1.269 — re-check if the CLI is much newer)

- Marketplace manifest lives at `.claude-plugin/marketplace.json`; plugin manifest at
  `<plugin>/.claude-plugin/plugin.json`. Both validate today.
- **There is no install-time hook.** A `postinstall` field validates as "Unknown field ... ignored at load time".
  Setup therefore happens on **first invocation**, driven by SKILL.md.
- **`userConfig` is real** and is prompted for after install; also settable via
  `claude plugin install --config key=value` and later `/plugin configure podcast`.
  Each option needs `title`, `type`, `description`; `default`/`required` optional; **`enum` is rejected**.
- Bundled-file path variable is **`${CLAUDE_PLUGIN_ROOT}`** (`CLAUDE_SKILL_DIR` also exists but is far less used).
- `hooks` is a recognised manifest field (path-validated) if a SessionStart hook is ever wanted.
- Validation gate: `claude plugin validate --strict <path>` (also `--json`); use in CI.
- Local testing without publishing: `claude --plugin-dir <path>` (also `--plugin-url <zip>`).
- Install for users: `/plugin marketplace add <owner>/<repo>` then `/plugin install podcast@podcast-skill`.

## 3. Layout

```
podcast-skill/
  .claude-plugin/marketplace.json              [done, validates]
  plugins/podcast/.claude-plugin/plugin.json   [done, validates - holds userConfig]
  plugins/podcast/skills/podcast/
    SKILL.md                 [DONE 2026-09-12]
    scripts/config.py        [in flight - agent A]   settings + detect() + status banner
    scripts/setup.sh         [in flight - agent A]   status | install <component> | doctor
    scripts/render.py        [in flight - agent B]   multi-engine TTS
    scripts/qa.py            [in flight - agent B]   whisper-cli or faster-whisper
    scripts/rawfetch.py      [DONE - was already clean]     verbatim page text for quote checking
    scripts/deliver.py       [DONE - scrubbed] Telegram, privacy-gated
    angles/*.md              [DONE - scrubbed]    interview-prep, learn-topic, company-diligence, product-research
    templates/               [DONE]                  listener.example.md, lexicon.txt, qa-ignore.txt
  README.md [DONE]  LICENSE [DONE]  CLAUDE.md [DONE]  PLAN.md
  .github/workflows/validate.yml   [DONE]  plugin validate --strict + all --selftest suites
```

## 4. Contracts (both builders were given these; keep them stable)

Paths: config `${XDG_CONFIG_HOME:-~/.config}/topic-podcast/config.json`; state
`${XDG_DATA_HOME:-~/.local/share}/topic-podcast/` with `venv/`, `models/`, `installed.json`.
Env overrides: `PODCAST_EPISODES_DIR`, `PODCAST_VOICE_ENGINE`, `PODCAST_QA_LEVEL`, `PODCAST_TELEGRAM_BOT`,
`PODCAST_LISTENER_PROFILE`, `PODCAST_STATE_DIR`, `PODCAST_CONFIG`.

`config.py` API: `load()`, `state_dir()`, `models_dir()`, `venv_python()`, `detect()`, `status()`,
`format_status()`, `save(updates)`; CLI `status [--json] | set k=v | path | --selftest`.

`setup.sh`: `status | install <voice-piper|voice-kokoro|qa-base|qa-small|qa-medium> [--yes] | doctor`.
Exit **0** ok, **3** user must install a system package (ffmpeg/espeak-ng), **1** failure. Never uses sudo.

Script exit codes: `render.py`/`qa.py` exit **3** = "not installed, offer the upgrade"; qa exit 1 = QA failed;
exit 2 = tool error. `deliver.py`: 3 privacy gate refused, 4 over 50 MB, 5 bad chapters.

## 5. Remaining tasks (in order)

**Done 2026-09-12:** manifests, SKILL.md, scrubs (angles, deliver.py), templates, README, LICENSE, CLAUDE.md, CI
(`.github/workflows/validate.yml` + `check_manifests.py`). **Left:** items 7-10 below, plus the two builder agents' files.

1. **SKILL.md** - the playbook, rewritten for other people. Must include: first-run banner (run
   `scripts/setup.sh status` and show it), the upgrade vocabulary (`upgrade voice`, `upgrade qa`,
   `configure telegram`, `status`), tier-0 behaviour (write the script, offer audio), and all pipeline steps
   (brief -> parallel research -> **verify against primary sources** -> script -> render -> QA -> deliver -> close).
   Paths via `${CLAUDE_PLUGIN_ROOT}`. Keep the verification discipline and the failure-modes table.
2. **Scrub `rawfetch.py`, `deliver.py`, `angles/*.md`** of names, employers, projects, handles, host paths.
3. **Templates**: `listener.example.md` (neutral), starter `lexicon.txt` (comments only), starter
   `qa-ignore.txt` (no personal names).
4. **README.md** - what it is, 60-second start, the tier table, privacy statement (nothing leaves the machine
   except the research web fetches and optional Telegram), model licences.
5. **CLAUDE.md** - for future sessions working on this repo.
6. **CI** - `claude plugin validate --strict` + four `--selftest` suites.
7. **Review one tier up (Opus)** of the builders' code, as with the original scripts.
8. **Stranger test** (section 7).
9. ~~Privacy gate -> create the private GitHub repo -> push~~ **DONE** (`sonugill79/podcast-skill`, private).
10. **Open:** only after real use, consider making it public. Before that: re-run the privacy gate, decide whether the
    author attribution and homepage URL should stay, and consider whether `PLAN.md`/`CLAUDE.md` (which name the private
    source project) should ship at all in a public repo.

**Left for a future session:** install it the way a stranger would (`/plugin marketplace add sonugill79/podcast-skill`
then `/plugin install podcast@podcast-skill`) in a scratch HOME and make one real episode through the installed
plugin rather than the working tree; measure kokoro-only footprint; the LOW nit where a *missing voice file* still
says "no voice engine installed".

## 6. Privacy gate (must pass before any push, and again before going public)

```bash
grep -rinE 'sonu|gill|remitly|oportun|trippits|finance-lens|shilshole|dmitri|3090|ai-bot|digesting|@gmail|/home/[a-z]+' \
  --exclude-dir=.git . | grep -vE '^\./(PLAN|CLAUDE)\.md'
```
Expect **zero** hits outside `PLAN.md`/`CLAUDE.md` (which may name the private source project) and the deliberate
author attribution in the two manifests (`owner`/`author`/`homepage`). CI enforces exactly this. Also confirm: no
episodes, no `listener.md` (only the example), no bot tokens or chat ids, no `deliver.json`.

## 7. Stranger test (the real acceptance test)

Run as if a new user, with a **temporary HOME** so nothing local leaks in:
```bash
export HOME=$(mktemp -d); claude --plugin-dir ~/projects/podcast-skill/plugins/podcast
```
1. `/podcast <topic>` with nothing installed -> banner shows voice/QA unavailable, the episode still produces a
   researched, verified **script**, and the transcript ends with a clear upgrade offer.
2. `upgrade voice` -> confirms size, installs, renders the same script to MP3 without re-running research.
3. `upgrade qa` -> installs, runs QA, reports coverage.
4. Re-run: setup is skipped, cache is reused.
5. `configure telegram` with no bots file -> refuses cleanly with instructions, never crashes.
Record the wall-clock time and download size of each step in the README.

## 7b. Measured facts (2026-09-12, Linux)

Verified package names and URLs: `piper-tts` 1.8.0, `kokoro-onnx` 0.6.1 (ships `espeakng-loader`, so **no system
espeak-ng is needed by either engine** — contrary to the original assumption), `faster-whisper` 1.2.1 with models from
`Systran/faster-whisper-{base,small,medium}`. Piper voices from `rhasspy/piper-voices` tag v1.0.0
(`en_US-amy-medium`, `en_US-ryan-high`); Kokoro from the `kokoro-onnx` release tag `model-files-v1.0`.

On-disk: shared venv 510 MB (voice runtime ~270 MB, QA runtime ~240 MB), Piper voices 176 MB, Kokoro model 338 MB,
whisper base 142 MB — ≈1.2 GB with everything. Fresh `install voice-piper --yes` ≈19 s, re-run ≈0.8 s;
`install qa-base --yes` ≈12 s, re-run ≈1.1 s. No published checksums exist for the model assets, so the installer
sanity-checks size instead. These numbers are quoted in README.md, plugin.json and SKILL.md — keep them in sync.

## 7c. Queued fixes (apply with the review findings)

- ~~banner sizes~~ — folded into the installer fix list (the banner must quote ≈375 MB piper, ≈575 MB qa-base,
  ≈1.2 GB everything; kokoro-only to be measured).
- `qa.py` invents a `models_dir()/ggml-<level>.bin` convention for whisper.cpp that `setup.sh` never provisions.
  Harmless (it falls through to faster-whisper) but either document it or drop it.

**Verified working 2026-09-12:** tier 0 with an empty state dir — `config.py status` prints the banner, `render.py
--dry-run` estimates length with no packages installed, and `render.py`/`qa.py` both exit **3** with the exact
upgrade sentence. (When checking exit codes, don't pipe the command — `$?` then belongs to the pipe's last stage.)

## 7d. Review round 1 results (2026-09-12)

`config.py` / `setup.sh`: **HOLD**, four HIGH findings, all being fixed:
1. **`detect()` lied about every component** — only model files were recorded, so deleting the venv or uninstalling
   the package still reported the capability as present, which then crashed mid-pipeline.
2. Two concurrent installs wiped each other's venv and both advised `sudo apt install python3-venv` wrongly.
3. `installed.json` lost updates under concurrency (3/3 reproductions) — an installed component vanished from the record.
4. The banner promised "Audio will be generated" while ffmpeg was missing.
Plus: advice that can never be satisfied (`qa_level=medium` with base installed), `voice_engine=none` shown as broken,
a documented download-resume that doesn't exist, floating pip versions against a header claiming pinned ones, a
`PermissionError` traceback from the banner on an unwritable state dir, and unvalidated env values.

Held up: no injection (component names, `PODCAST_*`, hostile paths), bash 3.2/macOS clean, simulated `python3-venv`
failure exits 3 with real guidance, zero-byte models caught, config precedence correct, no half-written file ever
appears at a final path.

**Measured (reviewer, more accurate than the builder's):** fresh `install voice-piper` 25.5 s cold / 0.74 s re-run;
`install qa-base` 27.2 s cold / 1.02 s re-run. Venv 199 MB with piper only, 433 MB with qa only, 510 MB with all
three. Piper-only footprint ≈375 MB; everything ≈1.2 GB. Venv versions are exactly piper-tts 1.8.0,
kokoro-onnx 0.6.1, faster-whisper 1.2.1. **These are the numbers quoted in README/plugin.json/SKILL.md.**

`render.py` / `qa.py`: **HOLD**, three HIGH findings, all being fixed:
1. Missing piper voice raised `FileNotFoundError` instead of the documented exit 3.
2. **The documented command could not work for anyone** — packages live in the managed venv, so `python3 render.py`
   raised `ModuleNotFoundError`. Fix: re-exec into the venv interpreter (SKILL.md now says scripts find their own runtime).
3. `lexicon.txt` / `qa-ignore.txt` defaulted to a path that does not exist in the plugin, killing the pronunciation
   loop and producing a **false** QA failure. Fix: default to the episode's own folder, fall back to `templates/`.

Held up under attack: cache isolation across engines (disjoint keys, correct re-render on voice/speed change,
rejection of planted or 0-byte cache entries), timing exact at both 22.05 kHz and 24 kHz, no injection via hostile
paths, correct exit codes across backend failures, all evasion tests still caught (including a duplicated segment at
coverage 0.9888 caught by EXTRA_AUDIO), and old-vs-new QA output byte-identical. One new selftest case was proved
**vacuous by mutation** and is being rewritten — a good reminder to mutation-check any test that guards a headline property.

## 7e. Round-2 verification (2026-09-12, by the orchestrating session)

`render.py`/`qa.py` fixes confirmed by hand: cold `python3 render.py` with no venv on PATH renders through the
managed venv (piper, 22.05 kHz, 62 KB MP3); a voice that was never downloaded exits 3 instead of a traceback;
`--help` documents the new lexicon lookup. Selftests 92 (render) / 113 (qa) / 36 (config).

Open nit (not worth a round on its own): a *missing voice file* reports "no voice engine installed" — true enough to
route the user to `upgrade voice`, but it should say the engine is installed and the voice isn't.

## 7f. What the stranger test caught that four reviews did not (2026-09-12)

First full run of `test/stranger.sh` from an empty state dir: tier 0 passed, `upgrade voice` installed cleanly —
and then **render still exited 3**. Root cause: a **piper-only venv has no `soundfile`**, which `render.py` requires
to write audio. Every earlier test passed because this machine's venv had soundfile pulled in by the kokoro install.
Both Opus reviews, both builders and my own spot checks missed it for the same reason: none of them started from a
state a real first-time user would have.

Compounding it, `render.py` reported the missing module as *"no voice engine installed"*, which sent the debugging
down the wrong path — the engine was fine and built successfully in-process.

**Lessons worth keeping:** (1) a component's dependency list must cover what the *consumer* imports, not just what the
engine needs; (2) an error message that names the wrong subsystem costs more than the bug; (3) the only test that
finds this class is one that starts from nothing — keep `test/stranger.sh` in CI-adjacent use, and always run it
against a **fresh** state dir before publishing.

## 8. Known risks

- ~~espeak-ng needed~~ — **disproved**: both engines bundle phonemization. `detect()` still reports it, informational only.
- Piper and Kokoro use different sample rates - the cache key includes engine + rate to prevent mixing.
- faster-whisper model downloads land in its own cache, not our models dir; `detect()` must look in both.
- macOS ships bash 3.2 - `setup.sh` must not use bash 4 syntax.
- First run costs the user Claude tokens for research agents (3 at quick depth); the README must say so.

## 9. Resuming in a new session

Read this file, then `CLAUDE.md`, then `plugins/podcast/skills/podcast/SKILL.md`. Check `git log` and the task list
in section 5 for what is done. The source of truth for the *pipeline's* behaviour is the private project
`~/projects/topic-podcast` (its `CLAUDE.md` and `episodes/` show two worked examples); this repo is its portable,
de-personalised twin.

**Commit discipline:** the primary checkout stays on `main` and a PreToolUse hook blocks commits there. Land work by
copying the tree into a worktree (`git worktree add --orphan -b v1 ../podcast-skill-v1` for the first commit), commit
there, then merge into `main`.
