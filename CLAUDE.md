# CLAUDE.md: podcast-skill

Portable, de-personalised twin of a working private pipeline. This repo is packaged as a Claude Code **plugin** and
also acts as its own **marketplace**. **Read `PLAN.md` first** — it holds the decisions, the verified plugin
mechanics, the file contracts, the privacy gate and the acceptance test.

## Non-negotiables

- **Nothing personal ships.** No names, handles, employers, projects, hostnames, tokens, chat ids or `/home/<user>`
  paths outside `PLAN.md`, `CLAUDE.md` and `LICENSE`. CI enforces this; run the grep in `PLAN.md` §6 before any push.
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
- Test as a stranger with a throwaway `HOME` (see `PLAN.md` §7) so local config can't mask a missing dependency.
- **Commits:** the primary checkout stays on `main` and a hook blocks commits there. Copy the tree into a worktree,
  commit there, then merge into `main`.
