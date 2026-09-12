#!/usr/bin/env bash
# setup.sh: installer for the optional voice + QA tiers of the `podcast` plugin.
#
#   setup.sh status
#   setup.sh install <component> [--yes]      voice-piper | voice-kokoro | qa-base | qa-small | qa-medium
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
  mkdir -p "$STATE_DIR"
  announced=0
  while true; do
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      echo "$$" > "$LOCK_DIR/pid" 2>/dev/null || true
      LOCK_HELD=1
      return 0
    fi
    if [ -d "$LOCK_DIR" ]; then
      age=$(( $(date +%s) - $(_dir_mtime "$LOCK_DIR") ))
      if [ "$age" -gt "$LOCK_STALE_SECS" ]; then
        echo "warning: reclaiming an install lock older than ${LOCK_STALE_SECS}s ($LOCK_DIR) -- the process that held it appears to be gone." >&2
        rm -rf "$LOCK_DIR"
        continue
      fi
    fi
    if [ "$announced" = "0" ]; then
      echo "another 'setup.sh install' is already running against $STATE_DIR -- waiting for it to finish (it will proceed automatically; a lock older than ${LOCK_STALE_SECS}s is reclaimed automatically) ..." >&2
      announced=1
    fi
    sleep 2
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

print_ffmpeg_hint() {
  echo "Install: brew install ffmpeg | sudo apt install ffmpeg" >&2
  echo "(other Linux: sudo dnf install ffmpeg  /  sudo pacman -S ffmpeg)" >&2
}

require_ffmpeg() {
  if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "ffmpeg is required to produce the final MP3 and is missing." >&2
    print_ffmpeg_hint
    exit 3
  fi
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
  if ! curl -fL -C - --retry 3 --retry-delay 2 -o "$tmp" "$url"; then
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
  "$PY" - "$INSTALLED_JSON" "$STATE_DIR" "$key" "$ok" "$@" <<'PYEOF'
import json, os, sys, time
path, state_dir, key, ok = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "true"
files = sys.argv[5:]
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
    "requires_venv": True,
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
  require_ffmpeg
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
  require_ffmpeg
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
  # Same class of gap as the audio-runtime one above, re-checked end-to-end
  # 2026-09-12 per the coordinator's request: qa.py unconditionally shells out to
  # `ffmpeg` to convert the episode audio to 16 kHz mono before either transcription
  # backend runs, regardless of whether a voice engine was ever installed on this
  # machine. A qa-only install (no voice component installed first) previously never
  # checked for ffmpeg at all, so it could pass `install qa-base --yes` cleanly and
  # still fail the first real QA run. (numpy IS already covered for qa-only:
  # faster-whisper pulls it in transitively via onnxruntime/ctranslate2 -- verified
  # by installing faster-whisper alone into an empty venv and importing numpy.)
  require_ffmpeg
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
    voice-piper|voice-kokoro|qa-base|qa-small|qa-medium) ;;
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
  esac
}

usage() {
  cat <<'EOF'
usage: setup.sh status [--json]
       setup.sh install <component> [--yes]
                 components: voice-piper | voice-kokoro | qa-base | qa-small | qa-medium
       setup.sh doctor
EOF
}

main() {
  cmd="${1:-}"
  [ $# -gt 0 ] && shift
  case "$cmd" in
    status) cmd_status "$@" ;;
    install) cmd_install "$@" ;;
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
