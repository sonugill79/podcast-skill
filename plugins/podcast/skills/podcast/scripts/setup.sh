#!/usr/bin/env bash
# setup.sh: installer for the optional voice + QA tiers of the `podcast` plugin.
#
#   setup.sh status
#   setup.sh install <component> [--yes]      ffmpeg-static | voice-piper | voice-kokoro |
#                                              qa-base | qa-small | qa-medium | audio
#   setup.sh autosetup [--only audio] [--json]  non-interactive, priority order, never aborts
#                                                on one component's failure -- see cmd_autosetup
#   setup.sh doctor
#
# Targets bash 3.2 (macOS ships nothing newer) as well as any Linux bash -- no
# associative arrays, no `${var,,}`, no `mapfile`/`readarray`, no process substitution
# assumed. Never touches system packages and never uses sudo: everything installable
# goes into a private venv + models directory under the state dir, downloaded with
# `curl -fL -C - --retry 3` (auto-resuming a `.part` left by an interrupted run) to a
# `.part` file and moved into place only once it has been size- and (for the four big
# model files) checksum-verified. `.part` files older than $LOCK_STALE_SECS are swept
# at the start of every `install` so an abandoned download doesn't linger and inflate
# `doctor`'s size report; a `.part` from a run that died moments ago is left alone so
# the very next `install` resumes it instead of restarting the download.
#
# `install` takes an exclusive lock ($STATE_DIR/.lock, plain `mkdir` -- portable to
# macOS, which has no `flock` CLI) for its whole duration, so two concurrent installs
# (crontab misfire, two terminals) queue instead of corrupting each other's venv or
# racing on installed.json's read-modify-write; a lock left behind by a killed process
# is detected by age and reclaimed rather than blocking forever.
#
# Exit codes: 0 done · 3 a system package the user must install by hand (never
# installed automatically) · 1 a real failure. Every failing branch says what to try
# next.
#
# Sources verified 2026-09-12 (also recorded next to each component's URLs below):
#   - piper-tts:    https://pypi.org/project/piper-tts/            (`pip install piper-tts`, pinned ==1.8.0)
#   - kokoro-onnx:  https://pypi.org/project/kokoro-onnx/          (`pip install kokoro-onnx`, pinned ==0.6.1)
#   - faster-whisper: https://pypi.org/project/faster-whisper/     (`pip install faster-whisper`, pinned ==1.2.1)
#   - piper voices: https://huggingface.co/rhasspy/piper-voices (tag v1.0.0)
#   - kokoro model: https://github.com/thewh1teagle/kokoro-onnx/releases (tag model-files-v1.0)
#   - whisper models: Systran/faster-whisper-{base,small,medium} on Hugging Face,
#     fetched by the `faster-whisper` package itself via huggingface_hub.
# All six URLs below were HEAD/GET-verified reachable (HTTP 200) as part of this work.
# The four big model files (both piper voices, both kokoro files) are additionally
# checked against a sha256 recorded below, computed from a verified-good download on
# 2026-09-12 -- no publisher-supplied checksum exists for any of them (checked the HF
# repo and the GitHub release page by hand), so a same-size-but-corrupt file no longer
# passes silently.
set -u
# HIGH1 (found by review, 2026-09-12): `autosetup | head -1` -- exactly what the
# skill was told to do -- closes stdout the moment `head` has its line. Without
# this, the next write to stdout (by us, or by `tee`/`cat` downstream of us) raises
# SIGPIPE and DIES, taking whatever install was in flight down with it and losing
# the failure reason down the now-dead pipe. Ignoring SIGPIPE here is inherited by
# every child this script starts (an ignored, not merely trapped, disposition
# survives exec), so `tee`/`cat` stop cleanly on EPIPE instead of being killed.
# Never removed: a closed reader must never be able to abort work in progress.
trap '' PIPE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PY="$SCRIPT_DIR/config.py"
PY="${PODCAST_PYTHON:-python3}"

# --- state paths (mirrors config.py's XDG resolution; kept in bash so setup.sh has
#     no dependency on the venv or on config.py succeeding first) ---
expand_tilde() {
  case "$1" in
    "~") printf '%s\n' "$HOME" ;;
    "~/"*) printf '%s\n' "${1/#\~/$HOME}" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

if [ -n "${PODCAST_STATE_DIR:-}" ]; then
  STATE_DIR="$(expand_tilde "$PODCAST_STATE_DIR")"
elif [ -n "${XDG_DATA_HOME:-}" ]; then
  STATE_DIR="$(expand_tilde "$XDG_DATA_HOME")/topic-podcast"
else
  STATE_DIR="$HOME/.local/share/topic-podcast"
fi
VENV_DIR="$STATE_DIR/venv"
MODELS_DIR="$STATE_DIR/models"
INSTALLED_JSON="$STATE_DIR/installed.json"
LOCK_DIR="$STATE_DIR/.lock"
# Generous vs. the biggest single download here (kokoro's ~340 MB of model files)
# even on a slow link, so a lock is only ever reclaimed from a genuinely dead process.
LOCK_STALE_SECS=1800

PIPER_VOICES_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
KOKORO_RELEASE_BASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

# Pinned versions (verified 2026-09-12 -- see header). Pinning means `doctor`'s
# `pip list` output always matches what was actually verified to work, instead of
# floating to whatever is newest on install day.
PIPER_TTS_PIN="piper-tts==1.8.0"
KOKORO_ONNX_PIN="kokoro-onnx==0.6.1"
NUMPY_PIN="numpy==2.5.3"
SOUNDFILE_PIN="soundfile==0.14.0"
FASTER_WHISPER_PIN="faster-whisper==1.2.1"

# Approximate sizes shown to the user before a download, and floors used to reject a
# truncated/corrupt file (see the sha256 checks in the four big model downloads for
# the stronger guarantee -- these MIN_BYTES floors are the fallback for files that
# have no recorded checksum, and the cheap first check for the ones that do).
QA_SIZE_LABEL_base="~575 MB"; QA_MIN_BYTES_base=100000000
QA_SIZE_LABEL_small="~950 MB (approx.)"; QA_MIN_BYTES_small=300000000
QA_SIZE_LABEL_medium="~1.9 GB (approx.)"; QA_MIN_BYTES_medium=800000000

# sha256 of a verified-good download, 2026-09-12 (see header comment).
SHA256_AMY_MEDIUM="b3a6e47b57b8c7fbe6a0ce2518161a50f59a9cdd8a50835c02cb02bdd6206c18"
SHA256_RYAN_HIGH="b3990d7606e183ec8dbfba70a4607074f162de1a0c412e0180d1ff60bb154eca"
SHA256_KOKORO_ONNX="7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5"
SHA256_KOKORO_VOICES="bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"

# --- ffmpeg-static (Linux) ---------------------------------------------------
# Source: github.com/BtbN/FFmpeg-Builds, verified 2026-09-12. Actively maintained
# via GitHub Actions (more reliable uptime than a single personal-site mirror),
# publishes a sha256 for every asset in one file per release, and ships both
# linux64 and linuxarm64 GPL *static* (non-"-shared", i.e. no bundled .so files to
# keep track of) builds. The "latest" release tag is a ROLLING auto-build -- unlike
# the piper/kokoro model files above, its contents change over time, so its
# checksum can NOT be hardcoded here; it's fetched fresh from checksums.sha256
# every install and verified against THAT, not a constant (see install_ffmpeg_static).
# Picked the "n9.0-latest" asset (the latest FFmpeg *9.0-branch* build within that
# rolling release) over "master-latest" (bleeding trunk, more likely to regress)
# for a bit more stability while still tracking bugfixes.
FFMPEG_LINUX_RELEASE_BASE="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest"
FFMPEG_LINUX_CHECKSUMS_URL="$FFMPEG_LINUX_RELEASE_BASE/checksums.sha256"
FFMPEG_ASSET_linux_x86_64="ffmpeg-n9.0-latest-linux64-gpl-9.0.tar.xz"
FFMPEG_ASSET_linux_aarch64="ffmpeg-n9.0-latest-linuxarm64-gpl-9.0.tar.xz"
# Verified 2026-09-12: linux64 archive was 150,109,916 bytes; smallest real BtbN
# linux asset seen (linuxarm64-lgpl-shared) was ~54 MB -- this floor sits well
# under both real sizes, purely to catch a near-empty/truncated download before
# the sha256 check (which is authoritative) even runs.
FFMPEG_MIN_BYTES=40000000

# --- ffmpeg-static (macOS, brew absent) --------------------------------------
# Source: osxexperts.net, verified 2026-09-12 -- confirmed to publish a NATIVE
# arm64 (Apple Silicon) build (not just x86_64 under Rosetta, which is all
# evermeet.cx offers) plus a separate x86_64 build, each with an inline sha256 on
# the page. ffmpeg and ffprobe are separate downloads there. This is the fallback
# used only when `brew` isn't on the machine -- brew is preferred (see
# install_ffmpeg_static) because it needs no Gatekeeper/quarantine/codesigning
# workaround at all. UNVERIFIED beyond research + a reachability check (HTTP 200 on
# the page and both listed asset URLs) -- this agent has no macOS machine to
# actually run this path on; treat it as best-effort until someone confirms it end
# to end. The checksum is scraped from the page (no stable .sha256 sidecar file
# exists there) with a regex tolerant of the exact wording changing slightly; if
# scraping fails outright (page redesigned) this falls back to a size-only sanity
# check rather than refusing to install.
FFMPEG_MACOS_PAGE="https://www.osxexperts.net/"

# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

die() { echo "error: $1" >&2; exit "${2:-1}"; }

confirm() {
  printf '%s ' "Proceed? [y/N]"
  # `read` with stdin closed/exhausted (a cron, a piped-in script) would otherwise
  # raise "ans: unbound variable" under `set -u` -- treat no-answer as "no".
  read -r ans || ans=""
  case "$ans" in
    y|Y|yes|YES|Yes) return 0 ;;
    *) return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# install lock -- one at a time against a given state dir
# ---------------------------------------------------------------------------
LOCK_HELD=0

_dir_mtime() {
  stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0
}

acquire_lock() {
  # HIGH6 (found by review, 2026-09-12): an unwritable state dir (chmod 555, a
  # read-only mount, wrong ownership) used to make `mkdir "$LOCK_DIR"` fail
  # forever, indistinguishable from "someone else holds it" -- an infinite spin
  # with no result file ever appearing, and the skill left waiting for something
  # that will never come. Fail this fast and loud instead: exit 3 (a condition the
  # user, not this script, has to fix) within one check, well under a second.
  if ! mkdir -p "$STATE_DIR" 2>/dev/null || [ ! -w "$STATE_DIR" ]; then
    echo "error: state dir $STATE_DIR is not writable -- can't take the install lock." >&2
    echo "Fix its permissions, or point elsewhere: export PODCAST_STATE_DIR=<a writable directory>" >&2
    exit 3
  fi
  announced=0
  waited=0
  while true; do
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      echo "$$" > "$LOCK_DIR/pid" 2>/dev/null || true
      LOCK_HELD=1
      return 0
    fi
    if [ -d "$LOCK_DIR" ]; then
      # A dead owner's lock is reclaimed the moment we notice, not after
      # LOCK_STALE_SECS -- `kill -0` (signal 0) just tests whether the pid exists,
      # portable to macOS, and never actually signals it.
      owner_pid=""
      [ -f "$LOCK_DIR/pid" ] && owner_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null)"
      if [ -n "$owner_pid" ] && ! kill -0 "$owner_pid" 2>/dev/null; then
        echo "warning: reclaiming an install lock held by pid $owner_pid, which is no longer running ($LOCK_DIR)." >&2
        rm -rf "$LOCK_DIR"
        continue
      fi
      age=$(( $(date +%s) - $(_dir_mtime "$LOCK_DIR") ))
      if [ "$age" -gt "$LOCK_STALE_SECS" ]; then
        echo "warning: reclaiming an install lock older than ${LOCK_STALE_SECS}s ($LOCK_DIR) -- the process that held it appears to be gone." >&2
        rm -rf "$LOCK_DIR"
        continue
      fi
    fi
    # Belt-and-braces cap even now that a dead owner is reclaimed immediately --
    # if something keeps mkdir failing for a reason that is neither "unwritable"
    # (already caught above) nor "a live owner", this still ends instead of
    # spinning forever.
    if [ "$waited" -ge "$LOCK_STALE_SECS" ]; then
      echo "error: waited ${LOCK_STALE_SECS}s for the install lock ($LOCK_DIR) and it never freed up. If nothing is actually installing, remove it by hand: rm -rf $LOCK_DIR" >&2
      exit 1
    fi
    if [ "$announced" = "0" ]; then
      echo "another 'setup.sh install' is already running against $STATE_DIR -- waiting for it to finish (it will proceed automatically; a lock held by a dead process, or older than ${LOCK_STALE_SECS}s, is reclaimed automatically) ..." >&2
      announced=1
    fi
    sleep 2
    waited=$((waited + 2))
  done
}

release_lock() {
  if [ "$LOCK_HELD" = "1" ]; then
    rm -rf "$LOCK_DIR"
    LOCK_HELD=0
  fi
}

need_yes_or_confirm() {
  # $1 = assume_yes flag ("1" or "0")
  if [ "$1" = "1" ]; then
    return 0
  fi
  confirm || { echo "aborted -- nothing changed."; exit 1; }
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    printf ''
  fi
}

# Apparent size of a directory in bytes, portably: GNU `du -sb` gives an exact
# apparent size; BSD/macOS `du` has no -b, so falls back to its 512-byte block
# count * 512 (block-rounded, not exact, but good enough for an autosetup byte
# estimate -- see run_component()).
_dir_size_bytes() {
  if du -sb "$1" >/dev/null 2>&1; then
    du -sb "$1" 2>/dev/null | awk '{print $1}'
  else
    du -s "$1" 2>/dev/null | awk '{print $1 * 512}'
  fi
}

# _ffmpeg_works [PATH]: does the ffmpeg at PATH (default: whatever "ffmpeg" means
# on PATH) actually run? The one check for "is ffmpeg available" used everywhere
# that question matters (_note_ffmpeg_for_later, install_audio,
# install_ffmpeg_static's own idempotency check) -- three separate bare
# `[ -x ]`/`command -v` checks used to exist and could disagree, so a
# present-but-broken binary (0-byte, wrong arch, a stale symlink) could be
# skipped as "already available" by one check and correctly flagged missing by
# another.
_ffmpeg_works() {
  "${1:-ffmpeg}" -version >/dev/null 2>&1
}

_ffmpeg_available() {
  _ffmpeg_works ffmpeg || _ffmpeg_works "$STATE_DIR/bin/ffmpeg"
}

# _note_ffmpeg_for_later: non-fatal. HIGH (found by a real desktop run,
# 2026-09-12): voice-piper/voice-kokoro/qa-* used to call require_ffmpeg (a hard
# exit 3) even though NONE of them need ffmpeg to INSTALL -- only later, to
# render (voice) or QA (transcribe). That turned one failed component
# (ffmpeg-static) into two: in `autosetup`'s "always" plan, ffmpeg-static
# failing left ffmpeg still missing, so voice-piper's own require_ffmpeg then
# refused too, reporting 0/2 succeeded instead of the 1/2 that was actually
# true (piper installs fine on its own). render.py/qa.py already fail cleanly
# with their own ffmpeg message at the point ffmpeg is actually needed, so
# nothing is lost by not gating the install on it here -- just note it.
_note_ffmpeg_for_later() {
  _ffmpeg_available || echo "note: ffmpeg isn't installed yet -- not needed to install this, but you'll need it before you can render/QA audio. Say \"install ffmpeg\", or: setup.sh install ffmpeg-static --yes"
}

# download URL DEST MIN_BYTES [SHA256]
# Skips work already done (an existing file at DEST that already meets MIN_BYTES, and
# the checksum too when one is given, is left alone). Downloads to DEST.part with
# `curl -C -` (auto-resume: appends from DEST.part's current size, or starts fresh if
# it doesn't exist) and only `mv`s it into place once it has been size- (and, when
# given, checksum-) verified. A network failure LEAVES the .part in place so the next
# run resumes instead of restarting; a file that fails size/checksum verification
# (actually corrupt, not just incomplete) has its .part removed so a bad resume base
# is never reused.
download() {
  url="$1"; dest="$2"; min_bytes="$3"; sha256="${4:-}"
  if [ -f "$dest" ]; then
    size=$(wc -c < "$dest" | tr -d ' ')
    if [ "$size" -ge "$min_bytes" ]; then
      if [ -z "$sha256" ] || [ "$(sha256_of "$dest")" = "$sha256" ]; then
        echo "  already have $(basename "$dest") ($size bytes) -- skipping"
        return 0
      fi
      echo "  $(basename "$dest") failed checksum verification -- re-downloading"
      rm -f "$dest"
    fi
  fi
  mkdir -p "$(dirname "$dest")"
  tmp="$dest.part"
  if [ -f "$tmp" ]; then
    echo "  resuming $(basename "$dest") from $(wc -c < "$tmp" | tr -d ' ') bytes ..."
  else
    echo "  downloading $(basename "$dest") ..."
  fi
  if ! curl -fL --proto '=https' --proto-redir '=https' -C - --retry 3 --retry-delay 2 -o "$tmp" "$url"; then
    die "download of $(basename "$dest") failed -- partial progress was kept at $(basename "$tmp") for the next run. Check your network and re-run: setup.sh install ..."
  fi
  size=$(wc -c < "$tmp" | tr -d ' ')
  if [ "$size" -lt "$min_bytes" ]; then
    rm -f "$tmp"
    die "downloaded $(basename "$dest") is only $size bytes (expected at least $min_bytes) -- the source may have moved, or the resumed partial was corrupt (now removed). Re-run setup.sh install to retry from scratch, or check $url in a browser."
  fi
  if [ -n "$sha256" ]; then
    actual="$(sha256_of "$tmp")"
    if [ "$actual" != "$sha256" ]; then
      rm -f "$tmp"
      die "$(basename "$dest") failed checksum verification after download (the bad partial has been removed). Re-run setup.sh install to retry from scratch."
    fi
  fi
  mv "$tmp" "$dest"
}

# Removes .part files older than LOCK_STALE_SECS under $MODELS_DIR. Only called at
# the start of cmd_install, which holds the install lock for its entire duration, so
# any .part file present is guaranteed to be from a run that is NOT currently active
# -- either abandoned long ago (safe to discard) or the one about to be resumed in
# the next few seconds by THIS run (too recent to be swept, so resume still works).
sweep_stale_parts() {
  [ -d "$MODELS_DIR" ] || return 0
  found=$(find "$MODELS_DIR" -name '*.part' -type f -mmin "+$((LOCK_STALE_SECS / 60))" 2>/dev/null)
  if [ -n "$found" ]; then
    echo "removing stale partial download(s) older than $((LOCK_STALE_SECS / 60)) minutes:" >&2
    echo "$found" | while IFS= read -r f; do
      [ -n "$f" ] && echo "  $f" >&2
    done
    find "$MODELS_DIR" -name '*.part' -type f -mmin "+$((LOCK_STALE_SECS / 60))" -delete 2>/dev/null || true
  fi
}

ensure_venv() {
  if [ -x "$VENV_DIR/bin/python3" ]; then
    return 0
  fi
  echo "creating virtual environment at $VENV_DIR ..."
  mkdir -p "$STATE_DIR"
  # pid-unique so this process's own diagnostic output is never clobbered by --
  # or clobbers -- another one; harmless in practice now that install is
  # lock-serialized, but cheap and worth keeping as defense in depth.
  errfile="$STATE_DIR/.venv-create.err.$$"
  if ! "$PY" -m venv "$VENV_DIR" 2>"$errfile"; then
    cat "$errfile" >&2
    rm -f "$errfile"
    rm -rf "$VENV_DIR"
    echo "error: could not create a Python virtual environment." >&2
    echo "Install: sudo apt install python3-venv | brew install python3   (Homebrew's python3 includes venv)" >&2
    exit 3
  fi
  rm -f "$errfile"
  "$VENV_DIR/bin/python3" -m pip install --upgrade pip -q || true
}

venv_pip() { "$VENV_DIR/bin/python3" -m pip "$@"; }

# record_installed KEY OK(true/false) FILE...
# FILE paths under STATE_DIR are stored relative to it (so the record survives the
# state dir moving); other absolute paths (e.g. a faster-whisper HF cache blob) are
# kept as-is. Every FILE listed here should be something that only exists while the
# component actually WORKS -- not just the model, but a package-owned file (a CLI
# entry point, or the package's own __init__.py) so `pip uninstall` is caught, not
# just the state dir being wiped by hand. requires_venv is unconditionally true:
# every component this script installs runs out of the venv, so config.py's
# _component_files_ok() additionally refuses to call it installed if venv/bin/python3
# is gone, even if every listed file still happens to be present.
# Call this only while the install lock (acquire_lock) is held -- it does an
# unlocked read-modify-write of installed.json, which is safe only because install
# is now serialized against itself.
record_installed() {
  key="$1"; ok="$2"; shift 2
  # RECORD_REQUIRES_VENV=false for a component that doesn't run out of the venv
  # (ffmpeg-static: sudo-free static binaries or a brew install, neither of which
  # has anything to do with our Python venv) -- everything else defaults true.
  "$PY" - "$INSTALLED_JSON" "$STATE_DIR" "$key" "$ok" "${RECORD_REQUIRES_VENV:-true}" "$@" <<'PYEOF'
import json, os, sys, time
path, state_dir, key, ok, requires_venv = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "true", sys.argv[5] == "true"
files = sys.argv[6:]
rel = []
for f in files:
    f = os.path.abspath(f)
    rel.append(os.path.relpath(f, state_dir) if f.startswith(state_dir + os.sep) else f)
try:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        data = {}
except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeDecodeError):
    data = {}
data[key] = {
    "ok": ok,
    "requires_venv": requires_venv,
    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "files": rel,
}
os.makedirs(os.path.dirname(path), exist_ok=True)
tmp = f"{path}.tmp-{os.getpid()}"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, sort_keys=True)
    fh.write("\n")
os.replace(tmp, path)
PYEOF
}

# render.py needs a numpy array to synthesize into and soundfile to write the
# resulting wav, regardless of WHICH voice engine is chosen -- this used to ride in
# only as kokoro-onnx's own transitive dependency (soundfile) or onnxruntime's
# (numpy), so a piper-only install produced a venv with numpy + onnxruntime +
# piper-tts but NO soundfile: the first "upgrade voice" a piper-only stranger did
# left them unable to render at all (found by the end-to-end stranger test,
# 2026-09-12). Installed explicitly, pinned, by both voice installers, and recorded
# as its own component so config.py's detect() can tell the truth if it's ever
# removed independently (e.g. a stray `pip uninstall soundfile`) of whichever voice
# component happened to trigger it.
_ensure_audio_runtime() {
  echo "installing shared audio runtime ($NUMPY_PIN $SOUNDFILE_PIN) ..."
  venv_pip install -q "$NUMPY_PIN" "$SOUNDFILE_PIN" || die "pip install $NUMPY_PIN $SOUNDFILE_PIN failed. Check your network, or try: $VENV_DIR/bin/python3 -m pip install $NUMPY_PIN $SOUNDFILE_PIN   to see the full error."
  numpy_pkg=$("$VENV_DIR/bin/python3" -c "import numpy, os; print(os.path.abspath(numpy.__file__))" 2>/dev/null) || numpy_pkg=""
  soundfile_pkg=$("$VENV_DIR/bin/python3" -c "import soundfile, os; print(os.path.abspath(soundfile.__file__))" 2>/dev/null) || soundfile_pkg=""
  audio_files=()
  [ -n "$numpy_pkg" ] && audio_files+=("$numpy_pkg")
  [ -n "$soundfile_pkg" ] && audio_files+=("$soundfile_pkg")
  if [ "${#audio_files[@]}" -gt 0 ]; then
    record_installed "audio-runtime" true "${audio_files[@]}"
  fi
}

# ---------------------------------------------------------------------------
# component installers
# ---------------------------------------------------------------------------

install_voice_piper() {
  assume_yes="$1"
  _note_ffmpeg_for_later
  echo "This installs $PIPER_TTS_PIN (small pure-Python package, no system espeak-ng"
  echo "needed -- verified 2026-09-12) and downloads two US English voices from"
  echo "Hugging Face: en_US-amy-medium (female, ~60 MB) and en_US-ryan-high (male,"
  echo "~115 MB) -- about 375 MB total on a fresh install (Python deps + venv + both"
  echo "voices; less if the venv/deps already exist from another component)."
  need_yes_or_confirm "$assume_yes"

  ensure_venv
  _ensure_audio_runtime
  echo "installing $PIPER_TTS_PIN ..."
  venv_pip install -q "$PIPER_TTS_PIN" || die "pip install $PIPER_TTS_PIN failed. Check your network, or try: $VENV_DIR/bin/python3 -m pip install $PIPER_TTS_PIN   to see the full error."

  dir="$MODELS_DIR/piper"
  mkdir -p "$dir"
  download "$PIPER_VOICES_BASE/en/en_US/amy/medium/en_US-amy-medium.onnx" "$dir/en_US-amy-medium.onnx" 40000000 "$SHA256_AMY_MEDIUM"
  download "$PIPER_VOICES_BASE/en/en_US/amy/medium/en_US-amy-medium.onnx.json" "$dir/en_US-amy-medium.onnx.json" 500
  download "$PIPER_VOICES_BASE/en/en_US/ryan/high/en_US-ryan-high.onnx" "$dir/en_US-ryan-high.onnx" 80000000 "$SHA256_RYAN_HIGH"
  download "$PIPER_VOICES_BASE/en/en_US/ryan/high/en_US-ryan-high.onnx.json" "$dir/en_US-ryan-high.onnx.json" 500

  echo "verifying with a short synthesis ..."
  smoke_wav="$STATE_DIR/.smoke-piper.wav"; smoke_err="$STATE_DIR/.smoke-piper.err"
  if ! printf 'Setup complete.' | "$VENV_DIR/bin/piper" -m "$dir/en_US-amy-medium.onnx" -c "$dir/en_US-amy-medium.onnx.json" \
       -f "$smoke_wav" >/dev/null 2>"$smoke_err"; then
    cat "$smoke_err" >&2
    rm -f "$smoke_wav" "$smoke_err"
    die "piper installed but failed to synthesize a test sentence -- see the error above. Try re-running: setup.sh install voice-piper --yes"
  fi
  rm -f "$smoke_wav" "$smoke_err"

  # $VENV_DIR/bin/piper (the console-script entry point pip creates) is recorded
  # alongside the model files specifically so `pip uninstall piper-tts` -- which
  # removes it but leaves the venv directory itself intact -- is caught by
  # config.py's _component_files_ok(), not just a deleted state dir.
  record_installed "voice-piper" true \
    "$dir/en_US-amy-medium.onnx" "$dir/en_US-amy-medium.onnx.json" \
    "$dir/en_US-ryan-high.onnx" "$dir/en_US-ryan-high.onnx.json" \
    "$VENV_DIR/bin/piper"
  echo "voice-piper installed."
}

install_voice_kokoro() {
  assume_yes="$1"
  _note_ffmpeg_for_later
  echo "This installs $KOKORO_ONNX_PIN + $SOUNDFILE_PIN (Python packages, no system"
  echo "espeak-ng needed -- verified 2026-09-12, it ships its own via the"
  echo "espeakng-loader wheel) and downloads the Kokoro-82M ONNX model (~310 MB) and"
  echo "its voice pack (~27 MB) from GitHub -- about 521 MB total on a fresh install"
  echo "(Python deps + venv + both files; less if the venv/deps already exist)."
  need_yes_or_confirm "$assume_yes"

  ensure_venv
  _ensure_audio_runtime
  echo "installing $KOKORO_ONNX_PIN ..."
  venv_pip install -q "$KOKORO_ONNX_PIN" || die "pip install $KOKORO_ONNX_PIN failed. Check your network, or try: $VENV_DIR/bin/python3 -m pip install $KOKORO_ONNX_PIN   to see the full error."

  dir="$MODELS_DIR/kokoro"
  mkdir -p "$dir"
  download "$KOKORO_RELEASE_BASE/kokoro-v1.0.onnx" "$dir/kokoro-v1.0.onnx" 200000000 "$SHA256_KOKORO_ONNX"
  download "$KOKORO_RELEASE_BASE/voices-v1.0.bin" "$dir/voices-v1.0.bin" 10000000 "$SHA256_KOKORO_VOICES"

  echo "verifying with a short synthesis ..."
  smoke_err="$STATE_DIR/.smoke-kokoro.err"
  if ! "$VENV_DIR/bin/python3" - "$dir" "$STATE_DIR/.smoke-kokoro.wav" >/dev/null 2>"$smoke_err" <<'PYEOF'
import sys
from kokoro_onnx import Kokoro
import soundfile as sf
d, out = sys.argv[1], sys.argv[2]
k = Kokoro(f"{d}/kokoro-v1.0.onnx", f"{d}/voices-v1.0.bin")
samples, sr = k.create("Setup complete.", voice="af_heart", speed=1.0, lang="en-us")
sf.write(out, samples, sr)
PYEOF
  then
    cat "$smoke_err" >&2
    rm -f "$STATE_DIR/.smoke-kokoro.wav"
    # Known failure mode, found while measuring footprints for this fix (2026-09-12):
    # kokoro-onnx's espeak-ng backend silently mis-resolves its bundled data path
    # when the venv's absolute path is very long (~200+ chars observed failing,
    # ~110 chars observed working) -- looks like a fixed-size buffer in the
    # underlying espeak-ng .so, not anything this script controls. It fails with
    # exactly this message: a hardcoded CI path ending in .../espeak-ng-data/phontab.
    if grep -q "espeak-ng-data" "$smoke_err" 2>/dev/null; then
      echo "This looks like a known kokoro-onnx/espeak-ng issue where a very long" >&2
      echo "install path (this one: $STATE_DIR, ${#STATE_DIR} chars) makes it silently" >&2
      echo "fall back to a nonexistent build-time default data path instead of its own." >&2
      echo "Try: export PODCAST_STATE_DIR=<a short path, e.g. ~/.topic-podcast> and re-run." >&2
    fi
    rm -f "$smoke_err"
    die "kokoro-onnx installed but failed to synthesize a test sentence -- see the error above. Try re-running: setup.sh install voice-kokoro --yes"
  fi
  rm -f "$STATE_DIR/.smoke-kokoro.wav" "$smoke_err"

  # The package's own __init__.py is recorded alongside the model files specifically
  # so `pip uninstall kokoro-onnx` -- which leaves the venv directory itself intact --
  # is caught by config.py's _component_files_ok(), not just a deleted state dir.
  # kokoro-onnx has no CLI entry point to point at (unlike piper), so this is found
  # by asking the venv's own interpreter, right after the smoke test proved it
  # importable.
  kokoro_pkg=$("$VENV_DIR/bin/python3" -c "import kokoro_onnx, os; print(os.path.abspath(kokoro_onnx.__file__))" 2>/dev/null) || kokoro_pkg=""
  if [ -n "$kokoro_pkg" ]; then
    record_installed "voice-kokoro" true "$dir/kokoro-v1.0.onnx" "$dir/voices-v1.0.bin" "$kokoro_pkg"
  else
    record_installed "voice-kokoro" true "$dir/kokoro-v1.0.onnx" "$dir/voices-v1.0.bin"
  fi
  echo "voice-kokoro installed."
}

install_qa() {
  assume_yes="$1"; level="$2"
  # qa.py unconditionally shells out to `ffmpeg` to convert the episode audio to
  # 16 kHz mono before either transcription backend runs -- but not until an
  # actual QA run, not to install this component (numpy IS needed to install,
  # and IS already covered for qa-only: faster-whisper pulls it in transitively
  # via onnxruntime/ctranslate2 -- verified by installing faster-whisper alone
  # into an empty venv and importing numpy). This used to be require_ffmpeg (a
  # hard exit 3) -- see _note_ffmpeg_for_later's comment for why that's wrong:
  # it turned one missing/failed ffmpeg into a REFUSAL to install a component
  # that doesn't need it yet.
  _note_ffmpeg_for_later
  size_label_var="QA_SIZE_LABEL_$level"; min_bytes_var="QA_MIN_BYTES_$level"
  size_label="${!size_label_var}"; min_bytes="${!min_bytes_var}"

  echo "This installs $FASTER_WHISPER_PIN (pulls in ctranslate2 + onnxruntime -- its"
  echo "runtime is the bulk of the download, much bigger than the model itself) and"
  echo "downloads the Systran/faster-whisper-$level model -- $size_label total on a"
  echo "fresh install (deps are shared across every qa-* level you install)."
  need_yes_or_confirm "$assume_yes"

  ensure_venv
  echo "installing $FASTER_WHISPER_PIN ..."
  venv_pip install -q "$FASTER_WHISPER_PIN" || die "pip install $FASTER_WHISPER_PIN failed. Check your network, or try: $VENV_DIR/bin/python3 -m pip install $FASTER_WHISPER_PIN   to see the full error."

  mkdir -p "$MODELS_DIR/whisper"
  echo "downloading/verifying the $level model (this also runs it once, transcribing silence, as a smoke test) ..."
  # Prints one absolute path per line: model.bin, then whichever of its snapshot
  # siblings exist (tokenizer.json etc -- recording more than just the blob means a
  # partially-pruned HF cache dir is caught, not just the blob going missing), then
  # the faster_whisper package's own __init__.py (so `pip uninstall faster-whisper`,
  # which leaves the venv directory intact, is caught too).
  qa_out=$("$VENV_DIR/bin/python3" - "$MODELS_DIR/whisper" "$level" "$min_bytes" <<'PYEOF'
import glob, os, sys
import numpy as np
models_dir, level, min_bytes = sys.argv[1], sys.argv[2], int(sys.argv[3])
from faster_whisper import WhisperModel
model = WhisperModel(level, device="cpu", compute_type="int8", download_root=models_dir)
pattern = os.path.join(models_dir, f"models--Systran--faster-whisper-{level}", "snapshots", "*", "model.bin")
matches = glob.glob(pattern)
if not matches:
    print("no model.bin found under " + pattern, file=sys.stderr)
    sys.exit(1)
model_path = os.path.realpath(matches[0])
size = os.path.getsize(model_path)
if size < min_bytes:
    print(f"model.bin is only {size} bytes (expected at least {min_bytes})", file=sys.stderr)
    sys.exit(1)
# Smoke test: transcribe 1s of silence straight from a numpy array -- proves the
# whole decode path works without needing ffmpeg or a sample audio file on disk.
list(model.transcribe(np.zeros(16000, dtype=np.float32), beam_size=1)[0])

out_files = [model_path]
# The friendly-named siblings (tokenizer.json etc) live next to the SYMLINK
# (snapshots/<hash>/model.bin), not next to the blob model_path was realpath'd to
# (blobs/<hash> has no siblings at all, just other hash-named blobs) -- look
# relative to matches[0], not model_path.
snapshot_dir = os.path.dirname(matches[0])
for extra in ("tokenizer.json", "vocabulary.txt", "config.json"):
    p = os.path.join(snapshot_dir, extra)
    if os.path.exists(p):
        out_files.append(os.path.realpath(p))
import faster_whisper as _fw
out_files.append(os.path.abspath(_fw.__file__))
for p in out_files:
    print(p)
PYEOF
) || die "faster-whisper model download/verification failed for '$level' -- see the error above. Re-run: setup.sh install qa-$level --yes"

  qa_files=()
  while IFS= read -r line; do
    [ -n "$line" ] && qa_files+=("$line")
  done <<QAEOF
$qa_out
QAEOF

  record_installed "qa-$level" true "${qa_files[@]}"
  echo "qa-$level installed."
}

# install_ffmpeg_static: a sudo-free ffmpeg+ffprobe. On macOS, prefers
# `brew install ffmpeg` (also sudo-free, and needs no Gatekeeper workaround) when
# Homebrew is present; otherwise falls back to a static download. Never touches
# system packages, never calls sudo. Exits 3 (never installed automatically, print
# the real command) for an unsupported OS/arch or when a network fetch genuinely
# can't be done -- e.g. a platform this script has no source for at all.
# extract_verified_binaries ARCHIVE KIND OUT_DIR WANTED...: HIGH2 (found by
# review, 2026-09-12) -- a crafted archive containing a symlink named e.g.
# "TOP/bin/ffmpeg" pointing at some file already on the local machine used to
# survive naively into $bin_dir, where `chmod +x` (which follows symlinks) then
# flipped the PERMISSIONS OF THE SYMLINK'S TARGET, and the smoke test executed
# it: a proven local file went 664 -> 775 and ran. Fixed by never using `tar`/
# `unzip` to write into a real directory at all: this reads archive members with
# Python's tarfile/zipfile, refuses anything that (a) is a path outside a plain
# "OK to write" shape (absolute, containing "..", or an empty segment) or (b) is
# not a plain regular file (rejects symlinks AND hardlinks AND devices/fifos --
# `isreg()`/checking the zip external-attr mode bit), and writes the verified
# bytes to a name WE choose (`os.path.basename` of our own requested member,
# never the archive's own path) so even a bug in the path check could not smuggle
# a write outside OUT_DIR. Finally checks the written file starts with a real
# ELF or Mach-O magic number. Prints one output path per WANTED, in order,
# still NOT executable -- the caller chmods +x only after this succeeds, and
# only runs -version (the last check) before moving the file into $bin_dir.
extract_verified_binaries() {
  archive="$1"; kind="$2"; out_dir="$3"; shift 3
  "$PY" - "$archive" "$kind" "$out_dir" "$@" <<'PYEOF'
import os, stat, sys, tarfile, zipfile

archive, kind, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
wanted = sys.argv[4:]

ELF_MAGIC = b"\x7fELF"
MACHO_MAGICS = (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",
                b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca")


def safe_member_path(name):
    if not name or os.path.isabs(name) or "\x00" in name:
        return False
    parts = name.replace("\\", "/").split("/")
    return not any(p in ("..", "") for p in parts)


os.makedirs(out_dir, exist_ok=True)
extracted = []
try:
    if kind == "tar":
        # tarfile.open("r:*") auto-detects and decompresses gzip/bz2/xz using
        # Python's own built-in `lzma` module (linked into the interpreter,
        # not the external `xz` binary) -- found by a real desktop run,
        # 2026-09-12: a separate `tar -tf` shell-out (just to learn the
        # archive's one top-level directory name, before calling this function)
        # was still on the path that runs, and system `tar` on a machine with
        # no `xz` CLI installed failed outright ("xz: Cannot exec"), and even
        # where it succeeds, THAT was the archive read this hardening never
        # covered -- the exact case review HIGH-2 was about. `wanted` is now a
        # path suffix (e.g. "bin/ffmpeg") resolved against the archive's own
        # single top-level entry, discovered here, in the one place that
        # actually reads the archive.
        with tarfile.open(archive, "r:*") as tf:
            members = tf.getmembers()
            top_level = set()
            for m in members:
                name = m.name.replace("\\", "/").strip("/")
                if name:
                    top_level.add(name.split("/", 1)[0])
            if len(top_level) != 1:
                print(f"archive does not have exactly one top-level entry (found {sorted(top_level)})",
                      file=sys.stderr)
                sys.exit(1)
            top = next(iter(top_level))
            by_name = {m.name.replace("\\", "/").strip("/"): m for m in members}
            for w in wanted:
                full_name = f"{top}/{w}"
                m = by_name.get(full_name)
                if m is None:
                    print(f"missing archive member: {full_name}", file=sys.stderr); sys.exit(1)
                if not safe_member_path(m.name):
                    print(f"refusing unsafe member path: {m.name}", file=sys.stderr); sys.exit(1)
                if not m.isreg():
                    print(f"refusing non-regular-file member (type {m.type!r}, "
                          f"symlink/hardlink/device are all rejected): {m.name}", file=sys.stderr)
                    sys.exit(1)
                src = tf.extractfile(m)
                if src is None:
                    print(f"could not read member: {full_name}", file=sys.stderr); sys.exit(1)
                out_path = os.path.join(out_dir, os.path.basename(w))
                with open(out_path, "wb") as out:
                    out.write(src.read())
                extracted.append(out_path)
    elif kind == "zip":
        with zipfile.ZipFile(archive) as zf:
            infos = {i.filename: i for i in zf.infolist()}
            for w in wanted:
                info = infos.get(w)
                if info is None:
                    print(f"missing archive member: {w}", file=sys.stderr); sys.exit(1)
                if not safe_member_path(info.filename):
                    print(f"refusing unsafe member path: {info.filename}", file=sys.stderr); sys.exit(1)
                mode = (info.external_attr >> 16) & 0xFFFF
                if mode and stat.S_ISLNK(mode):
                    print(f"refusing symlink member: {info.filename}", file=sys.stderr); sys.exit(1)
                out_path = os.path.join(out_dir, os.path.basename(w))
                with zf.open(info) as src, open(out_path, "wb") as out:
                    out.write(src.read())
                extracted.append(out_path)
    else:
        print(f"unknown archive kind: {kind}", file=sys.stderr); sys.exit(1)
except (tarfile.TarError, zipfile.BadZipFile, OSError) as e:
    print(f"could not read archive: {e}", file=sys.stderr); sys.exit(1)

for p in extracted:
    with open(p, "rb") as f:
        head = f.read(4)
    if head != ELF_MAGIC and head not in MACHO_MAGICS:
        print(f"extracted file does not look like a real executable "
              f"(magic bytes {head!r}, expected ELF or Mach-O): {p}", file=sys.stderr)
        sys.exit(1)
    print(p)
PYEOF
}

install_ffmpeg_static() {
  assume_yes="$1"
  os="$(uname -s)"
  arch="$(uname -m)"
  bin_dir="$STATE_DIR/bin"

  # Idempotent + fast on a re-run: download()'s own per-file skip logic only
  # covers the archive, not the extracted bin_dir/ffmpeg it's unpacked into, so
  # this is the check that actually makes a second `install ffmpeg-static` (or
  # `install audio`/`autosetup`, which both call this) skip straight past the
  # network entirely. Uses the one shared -version probe (_ffmpeg_works), not a
  # bare `[ -x ]`, so a present-but-broken binary is never mistaken for done.
  if _ffmpeg_works "$bin_dir/ffmpeg" && _ffmpeg_works "$bin_dir/ffprobe"; then
    echo "ffmpeg-static already installed and working -- skipping download."
    RECORD_REQUIRES_VENV=false record_installed "ffmpeg-static" true "$bin_dir/ffmpeg" "$bin_dir/ffprobe"
    echo "ffmpeg-static installed."
    return 0
  fi

  if [ "$os" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
    echo "Homebrew found -- this will run 'brew install ffmpeg' (no sudo, no Gatekeeper workaround needed)."
    need_yes_or_confirm "$assume_yes"
    echo "installing ffmpeg via Homebrew ..."
    brew install ffmpeg || die "brew install ffmpeg failed -- see the error above. Try running it yourself: brew install ffmpeg"
    prefix="$(brew --prefix ffmpeg 2>/dev/null)"
    brew_ffmpeg="$prefix/bin/ffmpeg"
    brew_ffprobe="$prefix/bin/ffprobe"
    if [ ! -x "$brew_ffmpeg" ] || [ ! -x "$brew_ffprobe" ]; then
      die "brew install ffmpeg reported success but ffmpeg/ffprobe weren't found under $prefix/bin. Try: brew doctor, then re-run setup.sh install ffmpeg-static --yes"
    fi
    RECORD_REQUIRES_VENV=false record_installed "ffmpeg-static" true "$brew_ffmpeg" "$brew_ffprobe"
    echo "ffmpeg-static installed (via Homebrew)."
    return 0
  fi

  mkdir -p "$bin_dir"
  # MED (found by review): download_dir PERSISTS across a killed run (so a
  # resumed .part survives, the whole point of download()'s resume support) --
  # only extract_dir, which never holds anything worth resuming, gets wiped
  # unconditionally on every attempt. These used to be the same directory, so
  # the wipe destroyed the largest file's .part before it ever got a chance to
  # resume.
  download_dir="$STATE_DIR/.ffmpeg-static-download"
  mkdir -p "$download_dir"
  extract_dir="$STATE_DIR/.ffmpeg-static-extract"
  rm -rf "$extract_dir"
  mkdir -p "$extract_dir"

  case "$os" in
    Linux)
      case "$arch" in
        x86_64|amd64) asset="$FFMPEG_ASSET_linux_x86_64" ;;
        aarch64|arm64) asset="$FFMPEG_ASSET_linux_aarch64" ;;
        *)
          rm -rf "$extract_dir"
          echo "error: no static ffmpeg source for Linux/$arch." >&2
          echo "Install: sudo apt install ffmpeg  (or your distro's equivalent)" >&2
          exit 3
          ;;
      esac
      echo "This downloads a static ffmpeg+ffprobe build for Linux/$arch: $asset"
      echo "(~150 MB download, ~343 MB once unpacked -- measured 2026-09-12)."
      echo "GPL-licensed (github.com/BtbN/FFmpeg-Builds) -- fetched at runtime, never redistributed."
      need_yes_or_confirm "$assume_yes"

      checksums_file="$extract_dir/checksums.sha256"
      echo "fetching the published checksum list ..."
      curl -fL --proto '=https' --proto-redir '=https' --retry 3 -o "$checksums_file" "$FFMPEG_LINUX_CHECKSUMS_URL" \
        || die "could not fetch checksums.sha256 -- check your network and re-run: setup.sh install ffmpeg-static --yes"
      expected="$(awk -v f="$asset" '$2==f {print $1}' "$checksums_file")"
      [ -n "$expected" ] || die "no checksum entry for $asset in the published checksums.sha256 -- the release layout may have changed. Check https://github.com/BtbN/FFmpeg-Builds/releases"

      archive="$download_dir/$asset"
      download "$FFMPEG_LINUX_RELEASE_BASE/$asset" "$archive" "$FFMPEG_MIN_BYTES" "$expected"

      echo "extracting ffmpeg + ffprobe ..."
      # No system `tar`/`xz` shell-out anywhere on this path (found by a real
      # desktop run, 2026-09-12, on a machine with no `xz` binary: a `tar -tf`
      # here, used only to learn the archive's top-level directory name, failed
      # outright with "xz: Cannot exec" -- and even where `xz` is present, that
      # call was outside extract_verified_binaries' hardening, i.e. exactly the
      # unguarded read review HIGH-2 was about). extract_verified_binaries now
      # discovers the top-level directory itself via Python's tarfile (which
      # decompresses .xz internally, no external `xz` needed) and takes
      # "bin/ffmpeg"/"bin/ffprobe" as suffixes -- see its comments.
      extracted="$(extract_verified_binaries "$archive" tar "$extract_dir" \
                     "bin/ffmpeg" "bin/ffprobe")" \
        || die "extracting $asset failed -- see the error above (nothing was installed). Re-run to retry: setup.sh install ffmpeg-static --yes"
      new_ffmpeg="$(printf '%s\n' "$extracted" | sed -n '1p')"
      new_ffprobe="$(printf '%s\n' "$extracted" | sed -n '2p')"
      rm -f "$archive"
      ;;
    Darwin)
      # brew absent -- fall back to a native-arm64-capable static source.
      # UNVERIFIED beyond research (see the FFMPEG_MACOS_PAGE comment above): no
      # macOS machine was available to actually run this branch end to end.
      case "$arch" in
        arm64) label="Apple Silicon" ;;
        x86_64) label="Intel" ;;
        *)
          rm -rf "$extract_dir"
          echo "error: no static ffmpeg source for macOS/$arch." >&2
          echo "Install: install Homebrew (https://brew.sh) then: brew install ffmpeg" >&2
          exit 3
          ;;
      esac
      echo "Homebrew not found. This downloads a static ffmpeg+ffprobe build for"
      echo "macOS/$arch from osxexperts.net (unofficial, ~80-150 MB) instead."
      echo "Apple Silicon requires an ad-hoc code-signing step after download (see below);"
      echo "installing Homebrew (https://brew.sh) and re-running is the more standard path."
      need_yes_or_confirm "$assume_yes"

      page="$extract_dir/osxexperts.html"
      curl -fL --proto '=https' --proto-redir '=https' --retry 3 -o "$page" "$FFMPEG_MACOS_PAGE" \
        || die "could not reach osxexperts.net -- check your network, or install Homebrew instead: https://brew.sh" 3

      # HIGH3 (found by review, 2026-09-12): a crafted `href` on this page used to
      # be `eval`'d directly (`eval "$found"`), so a value like
      # `https://.../ffmpeg$(curl evil|sh).zip` ran arbitrary shell before any
      # download even started. Fixed three ways: (1) never eval -- read the
      # python output line by line and assign via plain parameter expansion,
      # which cannot execute anything embedded in the value; (2) the URL is
      # regex-validated against an https/osxexperts.net-only allow-list below
      # before it's ever passed to curl; (3) no checksum found on the page is now
      # a hard refusal (exit 3), not a silent fall-back to a size-only check --
      # an unsupported path is fine, installing an unverified binary is not.
      FOUND=""; FFMPEG_URL=""; FFMPEG_SHA=""; FFPROBE_URL=""; FFPROBE_SHA=""
      while IFS= read -r found_line; do
        case "$found_line" in
          FOUND=*) FOUND="${found_line#FOUND=}" ;;
          FFMPEG_URL=*) FFMPEG_URL="${found_line#FFMPEG_URL=}" ;;
          FFMPEG_SHA=*) FFMPEG_SHA="${found_line#FFMPEG_SHA=}" ;;
          FFPROBE_URL=*) FFPROBE_URL="${found_line#FFPROBE_URL=}" ;;
          FFPROBE_SHA=*) FFPROBE_SHA="${found_line#FFPROBE_SHA=}" ;;
        esac
      done <<PYFOUND
$("$PY" - "$page" "$label" <<'PYEOF'
import re, sys
html = open(sys.argv[1], encoding="utf-8", errors="replace").read()
label = re.escape(sys.argv[2])

def find(tool):
    # HIGH3 continued: the URL capture is restricted to a safe filename charset
    # ([A-Za-z0-9_.-]) -- NOT "any character but a quote" as it was before the
    # review found a crafted `href` (containing `$(...)`) that this regex happily
    # captured whole. A real page never needs more than this charset in a
    # filename; a page that does is refused, not "captured and hoped for".
    pat = re.compile(
        r'href="(https://www\.osxexperts\.net/' + tool + r'[A-Za-z0-9_.-]*\.zip)"[^>]*>\s*Download\s+' + tool +
        r'\s+[\d.]+\s*\(' + label + r'\).*?SHA256 checksum of ' + tool + r' file\s*:?\s*\n?\s*([0-9a-fA-F]{64})',
        re.DOTALL | re.IGNORECASE)
    m = pat.search(html)
    return (m.group(1), m.group(2).lower()) if m else (None, None)

ffmpeg_url, ffmpeg_sha = find("ffmpeg")
ffprobe_url, ffprobe_sha = find("ffprobe")
if ffmpeg_url and ffprobe_url:
    print(f"FFMPEG_URL={ffmpeg_url}")
    print(f"FFMPEG_SHA={ffmpeg_sha or ''}")
    print(f"FFPROBE_URL={ffprobe_url}")
    print(f"FFPROBE_SHA={ffprobe_sha or ''}")
else:
    print("FOUND=0")
PYEOF
)
PYFOUND
      if [ "$FOUND" = "0" ] || [ -z "$FFMPEG_URL" ] || [ -z "$FFPROBE_URL" ]; then
        rm -rf "$extract_dir"
        die "could not find a $label download link on osxexperts.net -- the page may have changed. Install Homebrew instead: https://brew.sh, then: brew install ffmpeg" 3
      fi
      # HIGH3 continued (found by review, then found AGAIN in this fix's own
      # first draft, 2026-09-12): a plain `case URL in https://host/*.zip)` is
      # NOT an allow-list -- bash's `*` matches any bytes at all, so it happily
      # matched a crafted URL containing `$(...)` too (proven: it "passed" this
      # exact check before this tightening). The python regex above is now the
      # real allow-list (a fixed safe charset); this is redundant defense in
      # depth, so it also explicitly denies shell-metacharacter bytes rather
      # than relying on `*` to have not matched them.
      for check_url in "$FFMPEG_URL" "$FFPROBE_URL"; do
        case "$check_url" in
          https://www.osxexperts.net/*.zip) ;;
          *) rm -rf "$extract_dir"; die "refusing to download from an unexpected URL: $check_url" 3 ;;
        esac
        case "$check_url" in
          *'$'*|*'`'*|*'('*|*')'*|*';'*|*'|'*|*'&'*|*'<'*|*'>'*|*'"'*|*"'"*|*[[:space:]]*)
            rm -rf "$extract_dir"; die "refusing a download URL containing suspicious characters: $check_url" 3 ;;
        esac
      done
      if [ -z "$FFMPEG_SHA" ] || [ -z "$FFPROBE_SHA" ]; then
        rm -rf "$extract_dir"
        die "osxexperts.net's page didn't publish a readable sha256 for $label -- refusing to install an unverified binary. Install Homebrew instead: https://brew.sh, then: brew install ffmpeg" 3
      fi

      download "$FFMPEG_URL" "$download_dir/ffmpeg.zip" 20000000 "$FFMPEG_SHA"
      download "$FFPROBE_URL" "$download_dir/ffprobe.zip" 20000000 "$FFPROBE_SHA"
      extracted="$(extract_verified_binaries "$download_dir/ffmpeg.zip" zip "$extract_dir" ffmpeg)" \
        || die "extracting ffmpeg.zip failed -- see the error above (nothing was installed). Re-run to retry: setup.sh install ffmpeg-static --yes"
      new_ffmpeg="$(printf '%s\n' "$extracted" | sed -n '1p')"
      extracted="$(extract_verified_binaries "$download_dir/ffprobe.zip" zip "$extract_dir" ffprobe)" \
        || die "extracting ffprobe.zip failed -- see the error above (nothing was installed). Re-run to retry: setup.sh install ffmpeg-static --yes"
      new_ffprobe="$(printf '%s\n' "$extracted" | sed -n '1p')"
      rm -f "$download_dir/ffmpeg.zip" "$download_dir/ffprobe.zip"

      # Apple Silicon (and Gatekeeper-quarantined downloads generally) refuse to
      # run an unsigned/quarantined binary. xattr is a no-op when absent (nothing
      # to strip is not an error); codesign missing is NOT a no-op to silently
      # accept -- without it Apple Silicon fails LATER with an unexplained
      # "Killed: 9" at render time, so say so now instead.
      command -v xattr >/dev/null 2>&1 && xattr -dr com.apple.quarantine "$new_ffmpeg" "$new_ffprobe" 2>/dev/null
      if command -v codesign >/dev/null 2>&1; then
        codesign -s - "$new_ffmpeg" 2>/dev/null
        codesign -s - "$new_ffprobe" 2>/dev/null
      elif [ "$arch" = "arm64" ]; then
        echo "warning: 'codesign' not found (Xcode Command Line Tools aren't installed)." >&2
        echo "On Apple Silicon this ffmpeg WILL fail with 'Killed: 9' when run, unsigned." >&2
        echo "Install: xcode-select --install   then re-run: setup.sh install ffmpeg-static --yes" >&2
      fi
      ;;
    *)
      rm -rf "$extract_dir"
      echo "error: no static ffmpeg source for $os/$arch." >&2
      echo "Install: sudo apt install ffmpeg | brew install ffmpeg" >&2
      exit 3
      ;;
  esac

  echo "verifying (before making anything executable in $bin_dir) ..."
  chmod +x "$new_ffmpeg" "$new_ffprobe"
  smoke_err="$STATE_DIR/.smoke-ffmpeg.err"
  if ! "$new_ffmpeg" -version >/dev/null 2>"$smoke_err"; then
    cat "$smoke_err" >&2
    rm -f "$smoke_err"
    rm -rf "$extract_dir"
    die "the downloaded ffmpeg failed to run -- see the error above (nothing was installed). Re-run: setup.sh install ffmpeg-static --yes"
  fi
  rm -f "$smoke_err"

  mv -f "$new_ffmpeg" "$bin_dir/ffmpeg"
  mv -f "$new_ffprobe" "$bin_dir/ffprobe"
  rm -rf "$extract_dir"

  RECORD_REQUIRES_VENV=false record_installed "ffmpeg-static" true "$bin_dir/ffmpeg" "$bin_dir/ffprobe"
  echo "ffmpeg-static installed (GPL-licensed static build -- fetched at runtime, not redistributed)."
}

# install_audio: the one-command path from nothing to a renderable episode --
# ffmpeg-static (if not already present in ANY form, bundled or system) + the
# smaller/faster voice engine (piper). Idempotent: each half is skipped by its own
# installer's existing idempotency the moment it's already there, so a re-run (or
# a run where one half was already installed some other way) just confirms and
# moves on -- no separate "is this already done" logic needed here.
install_audio() {
  assume_yes="$1"
  if _ffmpeg_available; then
    echo "ffmpeg already available -- skipping ffmpeg-static."
  else
    # A failed ffmpeg-static is a WARNING here, not a hard stop -- run in a
    # subshell so its `exit`/`die` can't take install_audio (and the voice
    # engine it's about to install) down with it. The voice engine doesn't need
    # ffmpeg to install (see _note_ffmpeg_for_later), so a user who fixes ffmpeg
    # by hand later finds the voice already in place instead of having to
    # re-run everything.
    if ! ( install_ffmpeg_static "$assume_yes" ); then
      echo "warning: ffmpeg-static failed to install -- continuing to install the voice engine anyway (see the error above)." >&2
      echo "warning: install ffmpeg by hand, or re-run: setup.sh install ffmpeg-static --yes -- audio won't render until then." >&2
    fi
  fi
  install_voice_piper "$assume_yes"
  if _ffmpeg_available; then
    echo "audio installed (ffmpeg + piper voice)."
  else
    echo "piper voice installed, but ffmpeg is still missing -- see the warning above. Audio won't render until it's fixed."
  fi
}

# ---------------------------------------------------------------------------
# doctor / status / dispatch
# ---------------------------------------------------------------------------

print_tool_status() {
  name="$1"
  path="$(command -v "$name" 2>/dev/null || true)"
  if [ -n "$path" ]; then
    ver="$("$name" -version 2>&1 | head -1)"
    if [ -z "$ver" ]; then ver="$("$name" --version 2>&1 | head -1)"; fi
    echo "  $name: $path  ($ver)"
  else
    echo "  $name: missing"
  fi
}

cmd_doctor() {
  echo "== podcast setup doctor =="
  echo "OS: $(uname -s) $(uname -r)"
  echo "python3: $(command -v "$PY" 2>/dev/null || echo 'not found')  ($("$PY" --version 2>&1))"
  echo
  echo "-- system tools (never installed by this script) --"
  print_tool_status ffmpeg
  print_tool_status ffprobe
  print_tool_status espeak-ng
  print_tool_status curl
  echo "  (espeak-ng is informational only: neither piper-tts nor kokoro-onnx need a"
  echo "   system copy -- both bundle their own phonemization, verified 2026-09-12)"
  echo
  echo "-- state --"
  echo "state dir: $STATE_DIR"
  if [ -x "$VENV_DIR/bin/python3" ]; then
    echo "venv: present ($("$VENV_DIR/bin/python3" --version 2>&1))"
    echo "  packages: $(venv_pip list --disable-pip-version-check --format=freeze 2>/dev/null | tr '\n' ' ')"
  else
    echo "venv: not created yet (created automatically by the first 'setup.sh install')"
  fi
  if [ -d "$MODELS_DIR" ]; then
    echo "models dir: $MODELS_DIR ($(du -sh "$MODELS_DIR" 2>/dev/null | awk '{print $1}'))"
  else
    echo "models dir: not created yet"
  fi
  echo
  echo "-- installed components ($INSTALLED_JSON) --"
  if [ -f "$INSTALLED_JSON" ]; then
    "$PY" -m json.tool "$INSTALLED_JSON" 2>/dev/null || cat "$INSTALLED_JSON"
  else
    echo "(none yet -- run: setup.sh install <component> [--yes])"
  fi
  echo
  echo "-- config.py status --"
  "$PY" "$CONFIG_PY" status
}

cmd_status() {
  case "${1:-}" in
    --json) "$PY" "$CONFIG_PY" status --json ;;
    *) "$PY" "$CONFIG_PY" status ;;
  esac
}

cmd_install() {
  component="${1:-}"
  [ -n "$component" ] || { usage; exit 1; }
  shift || true
  assume_yes="0"
  for a in "$@"; do
    [ "$a" = "--yes" ] && assume_yes="1"
  done
  case "$component" in
    voice-piper|voice-kokoro|qa-base|qa-small|qa-medium|ffmpeg-static|audio) ;;
    *)
      echo "error: unknown component '$component'" >&2
      usage
      exit 1
      ;;
  esac

  # HIGH2/HIGH3: one install against a given state dir at a time -- otherwise two
  # concurrent installs can `rm -rf` each other's half-built venv and lose each
  # other's installed.json update. Held for the rest of the process's life; the EXIT
  # trap covers normal completion, `die`, and a signal.
  acquire_lock
  trap release_lock EXIT
  sweep_stale_parts

  case "$component" in
    voice-piper) install_voice_piper "$assume_yes" ;;
    voice-kokoro) install_voice_kokoro "$assume_yes" ;;
    qa-base) install_qa "$assume_yes" base ;;
    qa-small) install_qa "$assume_yes" small ;;
    qa-medium) install_qa "$assume_yes" medium ;;
    ffmpeg-static) install_ffmpeg_static "$assume_yes" ;;
    audio) install_audio "$assume_yes" ;;
  esac
}

# run_component NAME CMD...: runs CMD (an install_* function call) in a subshell
# so its `exit`/`die` on failure can never abort the rest of autosetup -- control
# always returns here. HIGH1 (found by review, 2026-09-12): this used to stream
# through `tee -a "$LOG_FILE"` so a caller could watch it live -- but that means
# CMD's own stdout is the same pipe autosetup's caller might close early (e.g.
# `autosetup | head -1`), and the SIGPIPE from writing into a closed pipe used to
# kill `tee` and, with it, the install in progress: a component would die with
# exit 141/whatever mid-download and the actual reason went down the dead pipe
# with it. Fixed at the source (this script now `trap '' PIPE` globally) AND
# here: CMD's output goes to $LOG_FILE ONLY now, never through a pipe to stdout,
# so there is nothing left for a closed stdout to break. Sets
# RC_OK/RC_BYTES/RC_ELAPSED for the caller to record. Bytes are measured as the
# state dir's total size delta across the run (not a precise "bytes over the
# wire", but a fair proxy, and the one number available without threading a
# counter back out of a subshell).
run_component() {
  name="$1"; shift
  before="$(_dir_size_bytes "$STATE_DIR")"; [ -z "$before" ] && before=0
  echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) starting $name ==" >> "$LOG_FILE"
  t0=$(date +%s)
  ( "$@" ) >>"$LOG_FILE" 2>&1
  rc=$?
  t1=$(date +%s)
  after="$(_dir_size_bytes "$STATE_DIR")"; [ -z "$after" ] && after=0
  RC_ELAPSED=$((t1 - t0))
  RC_BYTES=$((after - before))
  [ "$RC_BYTES" -lt 0 ] && RC_BYTES=0
  if [ "$rc" = "0" ]; then
    RC_OK=1
  else
    # Found by a real desktop run, 2026-09-12: a component that downloads a big
    # file and THEN fails (e.g. extraction) left that download's bytes on disk,
    # and they were reported as "bytes": 150117535 for a component whose
    # "ok": false -- bytes that were downloaded and discarded read as if they
    # were progress. A failed component reports 0 bytes; the log line above
    # still shows the real (pre-zeroing) disk delta for a human debugging it.
    RC_OK=0
    RC_BYTES=0
  fi
  echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) finished $name (exit $rc, ${RC_ELAPSED}s, ~$((after - before)) bytes on disk, reported as ${RC_BYTES}) ==" >> "$LOG_FILE"
}

# write_autosetup_result STATE MODE STARTED_AT ELAPSED TOTAL_BYTES TOTAL_DOWNLOAD_BYTES OK NAME:ATTEMPTED:OK:BYTES:ELAPSED...
# STATE is "running" or "done". HIGH5 (found by review, 2026-09-12): this used
# to be written only once, at the very end, so a reader mid-run (or mid a NEW
# run, right after a previous one finished) saw the PREVIOUS run's full
# "ok": true and could act on it as if the current one had already succeeded.
# Now called once before the loop (state=running, every planned component listed
# with attempted=false) and again after EACH component finishes (state=running,
# that component's real result filled in) before the final call (state=done).
# TOTAL_BYTES/TOTAL_DOWNLOAD_BYTES during "running" are the plan's pre-run
# ESTIMATE; the final "done" call passes the real measured total_bytes instead
# (see cmd_autosetup) -- there is no better real number for download bytes
# specifically, so that one stays the estimate throughout.
write_autosetup_result() {
  "$PY" - "$RESULT_FILE" "$LOG_FILE" "$@" <<'PYEOF'
import json, os, sys, time
result_path, log_file = sys.argv[1], sys.argv[2]
state, mode, started_at, elapsed, total_bytes, total_download_bytes, overall_ok = sys.argv[3:10]
components = {}
for spec in sys.argv[10:]:
    name, attempted, ok, bytes_, secs = spec.split(":")
    components[name] = {
        "attempted": attempted == "1",
        "ok": (ok == "1") if attempted == "1" else None,
        "bytes": int(bytes_),
        "elapsed_seconds": float(secs),
    }
data = {
    "state": state,
    "mode": mode,
    "started_at": started_at,
    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) if state == "done" else None,
    "elapsed_seconds": float(elapsed),
    "total_bytes": int(total_bytes),
    "total_download_bytes": int(total_download_bytes),
    "ok": (overall_ok == "1") if state == "done" else None,
    "components": components,
    "log_file": log_file,
}
tmp = f"{result_path}.tmp-{os.getpid()}"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, sort_keys=True)
    f.write("\n")
os.replace(tmp, result_path)
PYEOF
}

# cmd_autosetup [--only audio] [--json]: the non-interactive, background-safe
# entry point -- the skill launches this while research runs, no prompt, ever.
# Reads auto_setup + each setting's own choice via `config.py plan` (the single
# source of truth for "what's missing" -- see auto_setup_plan() in config.py, so
# this can never compute a different answer than `status --json` already showed
# the skill), announces exactly what it's about to download as its FIRST line
# (before any download starts, so the skill can quote it verbatim), then installs
# each missing piece in priority order (ffmpeg, voice, qa) via run_component,
# which never lets one component's failure stop the next. Always writes
# <state>/autosetup.log (progress, appended -- see write_autosetup_result on why
# not truncated) and <state>/autosetup-result.json (state, what was
# installed/failed, bytes, elapsed, updated per component -- see HIGH5 above) --
# a caller that redirects nothing and backgrounds this (`setup.sh autosetup &`)
# still gets both.
cmd_autosetup() {
  only=""
  json=0
  args=("$@")
  i=0
  while [ $i -lt ${#args[@]} ]; do
    case "${args[$i]}" in
      --only) i=$((i + 1)); only="${args[$i]:-}" ;;
      --json) json=1 ;;
    esac
    i=$((i + 1))
  done

  # HIGH4 (found by review, 2026-09-12): only the literal "audio" ever narrowed
  # scope -- `--only qa`, `--only voice`, a typo like `--only Audio`, all fell
  # through to NO narrowing at all and silently installed everything (~1.1 GB).
  # Validated here, at the actual CLI boundary, before config.py is even asked
  # for a plan -- config.py's own `plan` subcommand validates too (defense in
  # depth), but a bad value now never gets that far.
  case "$only" in
    ""|audio) ;;
    *)
      echo "error: --only expects 'audio' (or omit it entirely), got '$only'" >&2
      exit 2
      ;;
  esac

  acquire_lock
  trap release_lock EXIT
  sweep_stale_parts

  LOG_FILE="$STATE_DIR/autosetup.log"
  RESULT_FILE="$STATE_DIR/autosetup-result.json"
  # MED (found by review): APPEND, never truncate -- a previous run's log is
  # history a slow reader might not have caught up on yet, not garbage to
  # silently erase out from under them the moment a new run starts.
  echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) autosetup starting, pid $$ ==" >> "$LOG_FILE"

  plan_only_args=()
  [ "$only" = "audio" ] && plan_only_args=(--only audio)
  plan_json="$("$PY" "$CONFIG_PY" plan "${plan_only_args[@]}")" \
    || die "could not compute the auto-setup plan -- see the error above."

  # MED (found by review): FFMPEG_SIZE_BYTES used to be the archive's download
  # size alone, quoted as if it were the whole cost -- ffmpeg alone unpacks to
  # more than double that. config.py's plan now carries both totals; both are
  # shown here, "download" (wire) and "on disk" (final footprint), instead of
  # one number that undersold the truth by hundreds of MB.
  all_output="$("$PY" - "$plan_json" <<'PYEOF'
import json, sys
d = json.loads(sys.argv[1])
if not d["components"]:
    ann = ("auto-setup: auto_setup=never -- nothing will be installed automatically."
           if d["user_said_never"] else
           "auto-setup: nothing to do -- everything needed is already installed.")
else:
    names = ", ".join(c["component"] for c in d["components"])

    def fmt(n):
        return f"~{n / 1e9:.1f} GB" if n >= 1_000_000_000 else f"~{n / 1e6:.0f} MB"

    ann = (f"auto-setup: downloading {names} -- {fmt(d['total_download_bytes'])} download, "
           f"{fmt(d['total_bytes'])} on disk.")
print(ann)
print(f"MODE={d['mode']}")
print(f"PLAN_TOTAL_BYTES={d['total_bytes']}")
print(f"PLAN_TOTAL_DOWNLOAD_BYTES={d['total_download_bytes']}")
for c in d["components"]:
    print(f"PLAN_COMPONENT::{c['component']}:{c['kind']}:{c['target']}:{c['bytes']}")
PYEOF
)"

  announce="$(printf '%s\n' "$all_output" | head -1)"
  # HIGH1: at most this ONE line ever goes through `tee` to stdout. MED: in
  # --json mode the announcement goes to the log only -- the result file
  # (written with state=running right below, before any component runs) already
  # carries the same "what's about to happen" for a machine reader, so --json
  # mode's stdout ends up being exactly one JSON document (the final result),
  # never an early announce-json followed later by a second document.
  if [ "$json" = "1" ]; then
    printf '%s\n' "$announce" >> "$LOG_FILE"
  else
    printf '%s\n' "$announce" | tee -a "$LOG_FILE"
  fi

  MODE=""; PLAN_TOTAL_BYTES=0; PLAN_TOTAL_DOWNLOAD_BYTES=0
  while IFS= read -r line; do
    case "$line" in
      MODE=*) MODE="${line#MODE=}" ;;
      PLAN_TOTAL_BYTES=*) PLAN_TOTAL_BYTES="${line#PLAN_TOTAL_BYTES=}" ;;
      PLAN_TOTAL_DOWNLOAD_BYTES=*) PLAN_TOTAL_DOWNLOAD_BYTES="${line#PLAN_TOTAL_DOWNLOAD_BYTES=}" ;;
    esac
  done <<PLANVARS
$all_output
PLANVARS

  plan_components=()
  while IFS= read -r line; do
    case "$line" in
      PLAN_COMPONENT::*) plan_components+=("${line#PLAN_COMPONENT::}") ;;
    esac
  done <<PLANEOF
$all_output
PLANEOF

  started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  overall_start=$(date +%s)
  overall_ok=1
  total_actual_bytes=0
  ok_count=0
  result_entries=()
  attempted_count=${#plan_components[@]}

  if [ "$attempted_count" -eq 0 ]; then
    write_autosetup_result done "$MODE" "$started_at" 0 0 "$PLAN_TOTAL_DOWNLOAD_BYTES" 1
  else
    pending_entries=()
    for spec in "${plan_components[@]}"; do
      pending_entries+=("${spec%%:*}:0:0:0:0")
    done
    write_autosetup_result running "$MODE" "$started_at" 0 "$PLAN_TOTAL_BYTES" "$PLAN_TOTAL_DOWNLOAD_BYTES" 0 "${pending_entries[@]}"

    for spec in "${plan_components[@]}"; do
      name="${spec%%:*}"
      case "$name" in
        ffmpeg-static) run_component "$name" install_ffmpeg_static 1 ;;
        voice-piper) run_component "$name" install_voice_piper 1 ;;
        voice-kokoro) run_component "$name" install_voice_kokoro 1 ;;
        qa-base) run_component "$name" install_qa 1 base ;;
        qa-small) run_component "$name" install_qa 1 small ;;
        qa-medium) run_component "$name" install_qa 1 medium ;;
        *)
          echo "warning: autosetup doesn't know how to install '$name' -- skipping" >> "$LOG_FILE"
          RC_OK=0; RC_BYTES=0; RC_ELAPSED=0
          ;;
      esac
      result_entries+=("$name:1:$RC_OK:$RC_BYTES:$RC_ELAPSED")
      total_actual_bytes=$((total_actual_bytes + RC_BYTES))
      if [ "$RC_OK" = "1" ]; then
        ok_count=$((ok_count + 1))
      else
        overall_ok=0
        echo "warning: $name failed -- continuing with the rest (see $LOG_FILE for detail)." >&2
      fi

      # HIGH5 continued: update after EACH component, not just at the end -- the
      # skill can render as soon as ffmpeg+voice show done instead of waiting on
      # a 1.9 GB qa model that's still downloading behind them.
      still_pending=()
      for pending_spec in "${plan_components[@]}"; do
        pending_name="${pending_spec%%:*}"
        done_already=0
        for done_spec in "${result_entries[@]}"; do
          [ "${done_spec%%:*}" = "$pending_name" ] && done_already=1
        done
        [ "$done_already" = "0" ] && still_pending+=("$pending_name:0:0:0:0")
      done
      elapsed_so_far=$(( $(date +%s) - overall_start ))
      write_autosetup_result running "$MODE" "$started_at" "$elapsed_so_far" "$PLAN_TOTAL_BYTES" "$PLAN_TOTAL_DOWNLOAD_BYTES" 0 \
        "${result_entries[@]}" "${still_pending[@]}"
    done

    overall_elapsed=$(( $(date +%s) - overall_start ))
    write_autosetup_result done "$MODE" "$started_at" "$overall_elapsed" "$total_actual_bytes" "$PLAN_TOTAL_DOWNLOAD_BYTES" "$overall_ok" "${result_entries[@]}"
  fi

  if [ "$attempted_count" -eq 0 ]; then
    final_line="auto-setup: nothing installed (nothing was missing, or auto_setup=never)."
  else
    final_line="auto-setup: done -- $ok_count/$attempted_count succeeded, ${total_actual_bytes} bytes, ${overall_elapsed}s. Log: $LOG_FILE  Result: $RESULT_FILE"
  fi

  # MED: --json emits EXACTLY ONE machine-readable document (the result file's
  # content) -- never an early announce-json followed by human text followed by
  # a second JSON document.
  if [ "$json" = "1" ]; then
    printf '%s\n' "$final_line" >> "$LOG_FILE"
    cat "$RESULT_FILE"
  else
    printf '%s\n' "$final_line" | tee -a "$LOG_FILE"
  fi

  [ "$overall_ok" = "1" ]
}

usage() {
  cat <<'EOF'
usage: setup.sh status [--json]
       setup.sh install <component> [--yes]
                 components: ffmpeg-static | voice-piper | voice-kokoro | qa-base |
                             qa-small | qa-medium | audio (= ffmpeg-static + voice-piper)
       setup.sh autosetup [--only audio] [--json]
                 installs whatever auto_setup + the config says is missing, in the
                 background-safe, non-interactive, priority order: ffmpeg, voice, qa.
                 Never prompts. Log: <state>/autosetup.log
                 Result: <state>/autosetup-result.json
       setup.sh doctor
EOF
}

main() {
  cmd="${1:-}"
  [ $# -gt 0 ] && shift
  case "$cmd" in
    status) cmd_status "$@" ;;
    install) cmd_install "$@" ;;
    autosetup) cmd_autosetup "$@" ;;
    doctor) cmd_doctor "$@" ;;
    ""|-h|--help) usage ;;
    *)
      echo "error: unknown command '$cmd'" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
