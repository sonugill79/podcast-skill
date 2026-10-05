#!/bin/bash
# The deterministic layer of the pacing eval (see README.md). No voice engine, no ffmpeg, no QA model, stdlib only:
#   1. render.py --dry-run --strict (pacecheck) on every fixture, with the cast and pacing its brief.md names and
#      explicit voices, so nothing depends on local config or voice rotation;
#   2. check_sources.py: no Don't-air item said, no Reported item said without a hedge;
#   3. a negative control: one fixture with every [pause N] stripped must FAIL pacecheck (exit 4), or this gate
#      could not fail at all.
# Runs under a throwaway HOME and PODCAST_STATE_DIR so a developer's own settings can't mask anything.
# Exit 0 = all green, 1 = something failed. bash 3.2 compatible.
set -u
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
skill="$root/plugins/podcast/skills/podcast"
render="$skill/scripts/render.py"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/pacing-eval.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/home" "$tmp/state"
export HOME="$tmp/home" PODCAST_STATE_DIR="$tmp/state"

# Explicit voices per cast: each slot's first (the --no-rotate default) from casts/*.md.
voices_for() {
  case "$1" in
    two-host) echo 'MAYA=af_heart,ALEX=am_michael' ;;
    panel)    echo 'HOST=bf_lily,ADVOCATE=am_adam,SKEPTIC=af_kore' ;;
    solo)     echo 'NARRATOR=af_bella' ;;
    *)        echo '' ;;
  esac
}
field() {  # field <brief.md> <name> -> the value of "name: value"
  sed -n "s/^$2:[[:space:]]*//p" "$1" | head -n 1 | tr -d '\r'
}

fail=0 total=0 passed=0
printf '%-34s %-9s %-9s %s\n' fixture cast pacing result
for script in $(cd "$here/fixtures" && find . -name script.txt | sort); do
  script="${script#./}"
  dir="$here/fixtures/${script%/script.txt}"
  name="${dir#$here/fixtures/}"
  brief="$dir/brief.md"
  cast=$(field "$brief" cast); pacing=$(field "$brief" pacing); voices=$(voices_for "$cast")
  total=$((total + 1))
  if [ -z "$voices" ] || [ ! -f "$skill/casts/$cast.md" ]; then
    printf '%-34s %-9s %-9s %s\n' "$name" "$cast" "$pacing" 'FAIL (brief.md names no known cast)'; fail=1; continue
  fi
  out=$(python3 "$render" "$dir/script.txt" --dry-run --strict --cast "$skill/casts/$cast.md" \
          --voices "$voices" --pacing "${pacing:-relaxed}" 2>&1)
  rc=$?
  if [ $rc -eq 0 ]; then
    passed=$((passed + 1))
    est=$(printf '%s\n' "$out" | sed -n 's/^estimated duration: \([0-9:]*\).*/\1/p')
    printf '%-34s %-9s %-9s %s\n' "$name" "$cast" "$pacing" "pass ($est)"
  else
    printf '%-34s %-9s %-9s %s\n' "$name" "$cast" "$pacing" "FAIL (exit $rc)"
    printf '%s\n' "$out" | grep -E '⚠|^[^ ]*: ' | sed 's/^/    /'
    fail=1
  fi
done
echo "pacecheck --strict: $passed/$total fixtures pass"

echo
python3 "$here/check_sources.py" "$here/fixtures" || fail=1

# Negative control: strip every pause (whole-line and inline) from one fixture; pacecheck must say NO_PAUSE.
echo
ctl="$here/fixtures/learn-topic/informed/script.txt"
sed -e '/^\[pause [0-9.]*\]$/d' -e 's/ *\[pause [0-9.]*\]//g' "$ctl" > "$tmp/stripped.txt"
out=$(python3 "$render" "$tmp/stripped.txt" --dry-run --strict --cast "$skill/casts/two-host.md" \
        --voices "$(voices_for two-host)" --pacing relaxed 2>&1)
rc=$?
if [ $rc -eq 4 ] && printf '%s\n' "$out" | grep -q 'NO_PAUSE'; then
  echo "negative control: pauses stripped -> exit 4 with NO_PAUSE (the gate can fail)"
else
  echo "negative control: FAIL, a fixture with no pauses gave exit $rc; the gate cannot catch it"
  printf '%s\n' "$out" | sed 's/^/    /'
  fail=1
fi

[ $fail -eq 0 ] && echo 'pacing eval (deterministic): PASS' || echo 'pacing eval (deterministic): FAIL'
exit $fail
