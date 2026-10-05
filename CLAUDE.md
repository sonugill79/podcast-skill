# CLAUDE.md: podcast-skill

Portable, de-personalised twin of a working private pipeline. This repo is packaged as a Claude Code **plugin** and
also acts as its own **marketplace**. Phase decisions, file contracts and acceptance tests live in `docs/phases/`; the privacy gate is the "No personal
data" step in `.github/workflows/validate.yml`; the stranger acceptance test is `test/stranger.sh`.

## Non-negotiables

- **Nothing personal ships.** No names, handles, employers, projects, hostnames, tokens, chat ids or `/home/<user>`
  paths outside `CLAUDE.md` and `LICENSE`. CI enforces this; run the "No personal data" grep from `validate.yml` before any push.
- **Tier 0 must always work.** With no voice engine and no transcription installed, an episode still produces a
  researched, source-checked script. Never gate the pipeline behind an install.
- **Upgrades are named, sized and resumable.** The user says `upgrade voice`; they are told the size first; after
  installing, work continues from where it stopped rather than restarting research.
- **The installer never uses sudo** and never installs system packages. Missing `ffmpeg`/`espeak-ng` → exit 3 with the
  exact command for the user to run.
- **Verification is the product.** Anything quoted verbatim is confirmed with `rawfetch.py --grep` against the real
  page, not a summary.

## Layout

`plugins/podcast/` is the plugin: `.claude-plugin/plugin.json` (with `userConfig`), and `skills/podcast/` holding
`SKILL.md`, `scripts/`, `angles/` and `templates/`. `.claude-plugin/marketplace.json` at the repo root lists it.

`scripts/`: `config.py` (settings, detection, status banner) · `setup.sh` (status / install / doctor) ·
`render.py` (script → MP3, multiple voice engines) · `qa.py` (transcription round-trip with hard gates) ·
`rawfetch.py` (verbatim page text) · `deliver.py` (optional Telegram behind a privacy gate).

Every script has an offline `--selftest`; run them all after any change.

## Releasing

`claude plugin update` compares the **manifest version**, not the git commit. A fix merged without a version bump is
never served to anyone who already installed — the CLI says "already at the latest version" and keeps the cached copy.
**Every user-visible change bumps `version` in both `plugins/podcast/.claude-plugin/plugin.json` and the matching
entry in `.claude-plugin/marketplace.json`.** Verified end to end on 2026-09-12: 0.1.0 refused to update, 0.1.1 updated
and immediately picked up the fix.

## Working here

- Validate manifests with `claude plugin validate --strict plugins/podcast` and `... --strict .` before pushing.
- Test the plugin without publishing: `claude --plugin-dir <repo>/plugins/podcast`.
- Test as a stranger with a throwaway `HOME` (`test/stranger.sh`) so local config can't mask a missing dependency.
- **Commits:** the primary checkout stays on `main` and a hook blocks commits there. Copy the tree into a worktree,
  commit there, then merge into `main`.

## Phase work

- Phase docs live in `docs/phases/phase-<name>/`. Process gates: `docs/ops/phase-gates-addendum.md` (repo-specific instantiation of the `phase-gates` skill).
- `eval_suite: test/pacing/, threshold 90%`. Script-rule regression guard: fictional fixtures (3 angles × 3 levels plus a
  red-team brief), `rubric.md` and `README.md` (how to run it). `bash test/pacing/run.sh` is the deterministic layer
  (CI runs it, no engine); the judged layer is a Sonnet subagent scoring `rubric.md` at dev time, never in a user's
  episode. Go-live: ≥ 90% of fixtures pass the rubric and `pacecheck --strict`, 100% pass `qa.py` ≥ 0.96.
