#!/usr/bin/env bash
# stranger.sh — acceptance test: behave like someone who just installed the plugin and has nothing set up.
#
#   test/stranger.sh                 # throwaway state dir (downloads ~800 MB, slow but honest)
#   test/stranger.sh --reuse DIR     # reuse a state dir between runs (fast; still proves the tier logic)
#
# Exits non-zero on the first failed expectation. Every step prints PASS/FAIL and the elapsed seconds.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
S="$here/../plugins/podcast/skills/podcast/scripts"
work=$(mktemp -d); state=""; keep=0
[ "${1:-}" = "--reuse" ] && { state="$2"; keep=1; mkdir -p "$state"; }
[ -z "$state" ] && state="$work/state"
export PODCAST_STATE_DIR="$state" XDG_CONFIG_HOME="$work/config" PODCAST_EPISODES_DIR="$work/episodes"
mkdir -p "$XDG_CONFIG_HOME" "$PODCAST_EPISODES_DIR"
fails=0

say()  { printf '\n=== %s\n' "$1"; }
check(){ if [ "$2" = "$3" ]; then printf '  PASS %s (%s)\n' "$1" "$2"; else printf '  FAIL %s: got %s want %s\n' "$1" "$2" "$3"; fails=$((fails+1)); fi; }

cat > "$work/ep.txt" <<'SCRIPT'
# ── 1. Opening ─────────────
MAYA: Good morning. This is a test of the podcast plugin.
ALEX: Two speakers, one short segment, nothing else.
---
# ── 2. Close ───────────────
MAYA: That is the whole test.
SCRIPT

say "tier 0 — nothing installed"
python3 "$S/config.py" status > "$work/status0" 2>&1; check "config status runs" "$?" "0"
grep -qiE 'not installed|none' "$work/status0" && printf '  PASS banner reports missing capability\n' || { printf '  FAIL banner: %s\n' "$(head -3 "$work/status0")"; fails=$((fails+1)); }
grep -qiE 'upgrade voice' "$work/status0" && printf '  PASS banner tells the user how to upgrade\n' || { printf '  FAIL banner has no upgrade hint\n'; fails=$((fails+1)); }
python3 "$S/render.py" "$work/ep.txt" --dry-run >/dev/null 2>&1; check "dry-run works with no packages" "$?" "0"
python3 "$S/render.py" "$work/ep.txt" "$work/ep.mp3" >/dev/null 2>&1; check "render exits 3 (offer upgrade)" "$?" "3"
python3 "$S/qa.py" "$work/ep.txt" "$work/ep.mp3" >/dev/null 2>&1; check "qa exits 3 (offer upgrade)" "$?" "3"

say "upgrade voice"
t0=$SECONDS; bash "$S/setup.sh" install voice-piper --yes >"$work/inst1" 2>&1; rc=$?; printf '  (%ss)\n' "$((SECONDS-t0))"
check "install voice-piper" "$rc" "0"
grep -qiE 'MB|GB' "$work/inst1" && printf '  PASS install announced a size\n' || { printf '  FAIL install never mentioned a size\n'; fails=$((fails+1)); }
python3 "$S/render.py" "$work/ep.txt" "$work/ep.mp3" >/dev/null 2>&1; check "render now succeeds" "$?" "0"
[ -s "$work/ep.mp3" ] && printf '  PASS mp3 exists (%s bytes)\n' "$(wc -c < "$work/ep.mp3")" || { printf '  FAIL no mp3\n'; fails=$((fails+1)); }
[ -s "$work/ep.chapters.json" ] && printf '  PASS chapters.json written\n' || { printf '  FAIL no chapters.json\n'; fails=$((fails+1)); }

say "upgrade qa"
bash "$S/setup.sh" install qa-base --yes >"$work/inst2" 2>&1; check "install qa-base" "$?" "0"
python3 "$S/qa.py" "$work/ep.txt" "$work/ep.mp3" >"$work/qa1" 2>&1; rc=$?
check "qa runs and passes on clean audio" "$rc" "0"
grep -E '^coverage:' "$work/qa1" | head -1
[ "$rc" != 0 ] && { printf '  --- what qa reported:\n'; grep -vE '^\[' "$work/qa1" | tail -12 | sed 's/^/      /'; }

say "idempotency"
t0=$SECONDS; bash "$S/setup.sh" install voice-piper --yes >/dev/null 2>&1; rc=$?; d=$((SECONDS-t0))
check "re-install is a no-op" "$rc" "0"
[ "$d" -le 5 ] && printf '  PASS re-install fast (%ss)\n' "$d" || { printf '  FAIL re-install took %ss\n' "$d"; fails=$((fails+1)); }

say "telegram not configured"
python3 "$S/deliver.py" "$work/ep.mp3" --bot nope --dry-run >/dev/null 2>&1; rc=$?
[ "$rc" -ne 0 ] && printf '  PASS refuses cleanly (exit %s)\n' "$rc" || { printf '  FAIL delivered with no config\n'; fails=$((fails+1)); }

printf '\n%s\n' "-----------------------------------------"
[ "$keep" = 0 ] && printf 'state dir was throwaway: %s\n' "$state" || printf 'reused state dir: %s\n' "$state"
if [ "$fails" -eq 0 ]; then printf 'stranger test: ALL PASS\n'; else printf 'stranger test: %s FAILURE(S)\n' "$fails"; fi
exit "$fails"
