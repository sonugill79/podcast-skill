# Phase-Gates Addendum — podcast-skill
Generic process: the `phase-gates` skill. This file holds only podcast-skill-specific instantiations.

## Normalizer layer (Universal Clause 3 target)
- Settings: every read goes through `scripts/config.py` (`load()`, `DEFAULTS`, `ENUM_CHOICES`, `ENV_OVERRIDES`). No script reads env vars or the settings file directly.
- Script text: `render.py parse_script()` (the render side) and `qa.py parse_script_lines()`/`normalize()` (the QA side). A new script syntax must be taught to both.
- Constants shared by render and QA (e.g. `NONLEXICAL`) live in `config.py`.
- Diff-scoped review grep: `git diff -U0 main | grep '^+' | grep -nE 'os\.environ|getenv'` outside `config.py` → must be empty.

## Project-specific hostile-env rows
| # | Condition | Notes |
|---|---|---|
| P1 | Nothing installed (Tier 0) | the script must still be produced; exit 3 is an offer, not a failure |
| P2 | Throwaway `HOME` / `PODCAST_STATE_DIR` | `test/stranger.sh`; local config must not mask a missing dependency |
| P3 | Non-interactive `claude -p` | backgrounded renders die with the session; render in the foreground |
| P4 | piper instead of kokoro | old 0.1.2 installs |
| P5 | Episode with an existing `.tts-cache` and `cast.lock.json` | re-renders must stay cached and keep the same voices |
| P6 | macOS bash 3.2 | `setup.sh` must avoid `mapfile`, `declare -A` and `${x^^}` |

## Protected data
- The user's episodes folder (`config.episodes_dir`): existing `script.txt`, audio and `sources.md` are never overwritten. Write new files beside them.
- The private twin pipeline's episodes: read-only, except for new files written beside the originals.

## Mechanical pre-deploy checks
```bash
cd plugins/podcast/skills/podcast/scripts
for s in config.py render.py qa.py rawfetch.py deliver.py audition.py; do python3 $s --selftest || exit 1; done
cd - && claude plugin validate --strict plugins/podcast && claude plugin validate --strict .
python3 .github/check_manifests.py
# the privacy grep from .github/workflows/validate.yml ("No personal data" step)
test/stranger.sh --reuse <state-dir>
```
Bump `version` in BOTH `plugins/podcast/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`. Nothing is
pushed to the public repo without the owner's explicit go-ahead. Commits go in a worktree, never on `main` in the
primary checkout.

## Ramp/flag surfaces
- `userConfig` defaults (`default_cast`, `default_pacing`, `default_level`, `voice_engine`, `qa_level`, `auto_setup`). A default flip ships with the selftest that pins the old behaviour (e.g. `--pacing brisk` byte-identical to 0.2.0) in the same PR.
