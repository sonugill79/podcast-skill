#!/usr/bin/env python3
"""
config.py: resolved configuration + installed-tooling detection for the `podcast` plugin.

Stdlib only (no third-party imports at module load time) so this can be imported by
render.py/qa.py/deliver.py under either the system python3 or the state venv's
interpreter, and run standalone as a CLI before anything else is installed.

Resolution order for every setting, lowest to highest precedence:
  1. DEFAULTS (below)
  2. plugin install-time options -- the answers a user gave Claude Code's install
     prompts for plugin.json's userConfig, which Claude Code stores in ITS OWN
     settings files, not ours, and does NOT expose as environment variables in a
     normal session (only inside a hook's env) -- see _plugin_options().
  3. the config file: ${XDG_CONFIG_HOME:-~/.config}/topic-podcast/config.json
  4. an environment variable (PODCAST_EPISODES_DIR, PODCAST_VOICE_ENGINE, PODCAST_QA_LEVEL,
     PODCAST_TELEGRAM_BOT, PODCAST_LISTENER_PROFILE, PODCAST_AUTO_SETUP) -- set and
     non-empty wins outright.
Rationale for (2) sitting under our own config file and env: the install-time answer
must beat a built-in default, but an explicit local file or env override -- something
the user did on purpose, after the fact, on this machine -- should still win.
PODCAST_CONFIG overrides the config file's own path (used heavily by --selftest so it
never touches a real user config). PODCAST_STATE_DIR overrides the state directory
(venv/, models/, installed.json) the same way.

Everything this module writes to disk (config file, installed.json) is written to a
temp file in the same directory and then os.replace()'d into place, so a crash mid-write
never leaves a half-written file behind.

CLI:
  python3 config.py                    same as `status`
  python3 config.py status [--json]
  python3 config.py set key=value ...
  python3 config.py path               print the config file path
  python3 config.py --selftest         offline checks, PASS/FAIL per check, exit 0/1
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time

APP_NAME = "topic-podcast"

DEFAULTS = {
    "episodes_dir": "~/podcast-episodes",
    "voice_engine": "auto",
    "qa_level": "auto",
    "telegram_bot": "",
    "listener_profile": "",
    # Which cast (casts/<name>.md) an episode uses when the request doesn't name one.
    # The `debate` angle overrides it with `panel`, which is the cast it is written for.
    "default_cast": "two-host",
    # always: install whatever's missing (ffmpeg, then voice, then qa) in the
    # background the moment an episode needs it -- no prompt, nothing to ask for.
    # audio-only: same, but skip the qa model (ffmpeg + voice only).
    # never: install nothing implicitly; the explicit `setup.sh install <component>`
    # / "upgrade voice"/"upgrade qa" paths still work. See auto_setup_plan().
    "auto_setup": "always",
}

# env var name -> settings key. An env var that is unset OR set to the empty string is
# treated as "not overriding" -- an empty PODCAST_TELEGRAM_BOT, say, from a cron's
# environment shouldn't silently blank out a configured bot.
ENV_OVERRIDES = {
    "PODCAST_EPISODES_DIR": "episodes_dir",
    "PODCAST_VOICE_ENGINE": "voice_engine",
    "PODCAST_QA_LEVEL": "qa_level",
    "PODCAST_TELEGRAM_BOT": "telegram_bot",
    "PODCAST_LISTENER_PROFILE": "listener_profile",
    "PODCAST_DEFAULT_CAST": "default_cast",
    "PODCAST_AUTO_SETUP": "auto_setup",
}

# Worst -> best, "none" always first. Used both to validate `set` and to pick the best
# installed level under voice_engine=auto / qa_level=auto.
VOICE_LEVELS = ["none", "piper", "kokoro"]
QA_LEVELS = ["none", "base", "small", "medium"]
AUTO_SETUP_LEVELS = ["always", "audio-only", "never"]
ENUM_CHOICES = {"voice_engine": ["auto"] + VOICE_LEVELS, "qa_level": ["auto"] + QA_LEVELS,
                 "auto_setup": AUTO_SETUP_LEVELS}

VOICE_LABELS = {"piper": "fast, smaller download", "kokoro": "best quality"}

# Sizes quoted in the banner/prompts. These are total *fresh-install footprint*
# (venv + pip deps + model files), not just the model download, because the deps
# (onnxruntime, ctranslate2, ...) dominate for qa-* and are not small for voice
# either -- a size that only counted the model file would badly undersell the
# download. Measured 2026-09-12 with an empty state dir, one component at a time,
# via `du -sh` on the resulting state dir:
#   piper-only  (venv + piper-tts + both voices)        ~375 MB
#   kokoro-only (venv + kokoro-onnx + soundfile + model) ~521 MB
#   qa-base     (venv + faster-whisper + base model)     ~575 MB
#   everything installed together (shared venv)         ~1.2 GB
# qa-small/qa-medium were not measured standalone; estimated as the qa-base
# dependency overhead (~575-142=433 MB of shared venv/deps) plus the documented
# model size (small ~484 MB, medium ~1.5 GB per faster-whisper/openai-whisper) --
# flagged "approx." below rather than presented as measured.
VOICE_SIZE_HINTS = {"piper": "~375 MB", "kokoro": "~521 MB"}
QA_SIZE_HINTS = {"base": "~575 MB", "small": "~950 MB (approx.)", "medium": "~1.9 GB (approx.)"}

# Numeric (bytes) counterparts of the hints above, used by auto_setup_plan() to
# total an estimated download before anything runs. DOWNLOAD = bytes over the
# wire; DISK = final footprint once unpacked/installed -- these genuinely
# differ (a review on 2026-09-12 measured ffmpeg's own static archive at
# 150,109,916 bytes downloaded but 342,771,408 bytes once its two binaries are
# unpacked -- 2.3x -- and called a single announced number that undersold the
# true cost "the single thing most likely to make a user distrust the next
# announcement"). ffmpeg's pair is exact, measured. voice/qa's DISK numbers are
# the same measured *_SIZE_HINTS footprints as above; their DOWNLOAD numbers are
# comment-flagged estimates (model files downloaded are measured/exact -- see
# setup.sh's sha256 constants' sizes -- but the pip wheel portion of a fresh venv
# is not, so these are not claimed as precisely measured the way ffmpeg's are).
FFMPEG_DOWNLOAD_BYTES = 150_109_916
FFMPEG_DISK_BYTES = 342_771_408
VOICE_DOWNLOAD_BYTES = {"piper": 314_000_000, "kokoro": 474_000_000}  # approx.
VOICE_DISK_BYTES = {"piper": 375_000_000, "kokoro": 521_000_000}
QA_DOWNLOAD_BYTES = {"base": 528_000_000, "small": 870_000_000, "medium": 1_750_000_000}  # approx.
QA_DISK_BYTES = {"base": 575_000_000, "small": 950_000_000, "medium": 1_900_000_000}


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _xdg_config_home():
    return os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")


def _xdg_data_home():
    return os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")


def config_path():
    """Path to the config file, honoring PODCAST_CONFIG."""
    override = os.environ.get("PODCAST_CONFIG")
    if override:
        return os.path.expanduser(override)
    return os.path.join(_xdg_config_home(), APP_NAME, "config.json")


def _state_root():
    override = os.environ.get("PODCAST_STATE_DIR")
    if override:
        return os.path.expanduser(override)
    return os.path.join(_xdg_data_home(), APP_NAME)


def state_dir():
    """State directory (venv/, models/, installed.json). Created on demand. Never
    raises -- an unwritable/unreachable state dir (e.g. XDG_DATA_HOME pointing at a
    read-only mount) is surfaced by detect()/format_status() as a warning instead of
    crashing the first thing a stranger runs (see _dir_problem())."""
    d = _state_root()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def models_dir():
    d = os.path.join(state_dir(), "models")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def _dir_problem(d):
    """None if `d` exists and is actually writable; otherwise a short human-readable
    reason. Re-attempts makedirs (cheap, idempotent) since state_dir()/models_dir()
    swallow that error -- this is the one place it's allowed to surface."""
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, f".writetest-{os.getpid()}")
        with open(probe, "w", encoding="utf-8"):
            pass
        os.remove(probe)
        return None
    except OSError as e:
        return e.strerror or str(e)


def venv_python():
    """Path to the state venv's python3, or None if the venv hasn't been created yet.
    Same layout on macOS and Linux (bin/python3) -- this project targets both, not
    Windows, so no Scripts/ fallback is needed."""
    exe = os.path.join(_state_root(), "venv", "bin", "python3")
    return exe if os.path.exists(exe) else None


def _atomic_write_json(path, data):
    # os.path.dirname("bare.json") is "" -- os.makedirs("") raises FileNotFoundError,
    # not "already exists", so a config path with no directory component needs the
    # explicit "." fallback.
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Config: load / save
# ---------------------------------------------------------------------------

def _read_json_file(path):
    """A dict if `path` exists and holds a JSON object, else None. Every failure
    mode (missing, unreadable, not valid JSON, valid JSON but not an object) is a
    silent None -- never a traceback. Shared by _read_config_file() and
    _plugin_options() so both settings sources fail the same, safe way."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def _read_config_file():
    return _read_json_file(config_path()) or {}


# Plugin.json's own name; matched as a PREFIX (see _plugin_options()) rather than
# an exact "podcast@<marketplace>" string, so a fork installed under a different
# marketplace name is still picked up.
PLUGIN_NAME_PREFIX = "podcast@"


def _claude_settings_paths():
    """Claude Code settings files that may hold this plugin's install-time
    userConfig answers (pluginConfigs[...].options), most-specific first --
    mirrors Claude Code's own settings precedence (local project > shared project
    > user), so if the same key somehow appears in more than one, the more
    specific file wins. Project files are resolved relative to the CURRENT
    directory, so this only finds them when config.py happens to run from inside
    (or under) the project the user is working in -- a reasonable "easy to
    locate" reading of the request, not an exhaustive upward search."""
    paths = [
        os.path.join(os.getcwd(), ".claude", "settings.local.json"),
        os.path.join(os.getcwd(), ".claude", "settings.json"),
    ]
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        paths.append(os.path.join(os.path.expanduser(config_dir), "settings.json"))
    else:
        paths.append(os.path.expanduser("~/.claude/settings.json"))
    return paths


def _plugin_options():
    """This plugin's install-time userConfig answers (episodes_dir, voice_engine,
    ...), as Claude Code recorded them under pluginConfigs in one of its own
    settings files -- NOT ours, and NOT exposed as environment variables outside a
    hook, so this is the only way config.py can see them at all. Checked in
    _claude_settings_paths() order; the first file with a matching, well-formed
    entry wins (no merging across files). Every file is read via _read_json_file()
    (defensive: missing/unreadable/malformed is a silent skip) and every shape
    mismatch along the way (pluginConfigs not an object, an entry not an object,
    options not an object) is likewise skipped rather than raised."""
    for path in _claude_settings_paths():
        data = _read_json_file(path)
        if not data:
            continue
        plugin_configs = data.get("pluginConfigs")
        if not isinstance(plugin_configs, dict):
            continue
        for name, entry in plugin_configs.items():
            if not isinstance(name, str) or not name.startswith(PLUGIN_NAME_PREFIX):
                continue
            if not isinstance(entry, dict):
                continue
            options = entry.get("options")
            if isinstance(options, dict):
                return options
    return {}


def _apply_known_settings(cfg, updates, source_label):
    """Merge `updates` into `cfg`, keeping only known DEFAULTS keys with a
    string value that passes the same enum validation `set`/env use -- an
    unknown key is silently ignored (forward/backward compatible with a newer
    plugin.json), and an invalid value for a known key warns to stderr and keeps
    whatever `cfg` already had, exactly like an invalid env var does."""
    for k, v in updates.items():
        if k not in DEFAULTS:
            continue
        if not isinstance(v, str):
            print(f"warning: {source_label} value for {k!r} is not a string ({v!r}) -- ignoring",
                  file=sys.stderr)
            continue
        choices = ENUM_CHOICES.get(k)
        if choices and v not in choices:
            print(f"warning: {source_label} {k}={v!r} is not one of {', '.join(choices)} -- "
                  f"ignoring it, using {cfg[k]!r}", file=sys.stderr)
            continue
        cfg[k] = v


def load():
    """Resolved settings: DEFAULTS -> plugin install-time options -> config file ->
    environment (see the module docstring for why plugin options sit there)."""
    cfg = dict(DEFAULTS)
    _apply_known_settings(cfg, _plugin_options(), "plugin install option")
    file_cfg = _read_config_file()
    for k, v in file_cfg.items():
        if k in DEFAULTS:
            cfg[k] = v
    for env_name, key in ENV_OVERRIDES.items():
        val = os.environ.get(env_name)
        if not val:
            continue
        choices = ENUM_CHOICES.get(key)
        if choices and val not in choices:
            # e.g. PODCAST_VOICE_ENGINE=pipr (typo) must not silently resolve as if
            # it were "auto" -- warn and keep whatever load() had already resolved
            # from the config file/defaults.
            print(f"warning: {env_name}={val!r} is not one of {', '.join(choices)} -- "
                  f"ignoring it, using {cfg[key]!r}", file=sys.stderr)
            continue
        cfg[key] = val
    # abspath (not just expanduser) so a relative episodes_dir set via `set` or env
    # from some other cwd doesn't quietly become relative to whatever cwd a later
    # script happens to run from.
    cfg["episodes_dir"] = os.path.abspath(os.path.expanduser(cfg["episodes_dir"]))
    if cfg["listener_profile"]:
        cfg["listener_profile"] = os.path.abspath(os.path.expanduser(cfg["listener_profile"]))
    return cfg


def save(updates):
    """Merge `updates` (only known keys) into the config file and return the new
    resolved config (i.e. load() after the write -- env overrides still apply)."""
    cfg = _read_config_file()
    for k, v in updates.items():
        if k in DEFAULTS:
            cfg[k] = v
    _atomic_write_json(config_path(), cfg)
    return load()


# ---------------------------------------------------------------------------
# Detection: what is actually installed
# ---------------------------------------------------------------------------

def _which(*names):
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def _installed_record():
    path = os.path.join(state_dir(), "installed.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def _component_files_ok(entry):
    """True if setup.sh recorded this component as ok AND it can actually still run:
    every file it listed is present and non-empty (catches the state dir being
    partially wiped by hand, or the HF snapshot dir for a qa-* model being pruned --
    setup.sh records the model blob AND its sibling files, not just the blob), AND,
    for anything that runs out of the venv (every component today), the venv itself
    still exists (catches `rm -rf` of the whole venv, or `pip uninstall` of the
    specific package -- setup.sh additionally records a package-owned file, e.g.
    venv/bin/piper or the installed package's __init__.py, precisely so that a
    `pip uninstall` -- which leaves the venv directory itself intact -- still fails
    this check). A capability must never be reported present unless it can actually
    run: reporting "installed" from stale bookkeeping is what let render.py/qa.py
    crash on a capability that had quietly stopped existing.

    Paths are relative to state_dir() unless already absolute (qa-* models live
    under a content-addressed HF cache path that setup.sh records absolutely)."""
    if not entry or not entry.get("ok"):
        return False
    if entry.get("requires_venv", True) and venv_python() is None:
        return False
    sd = state_dir()
    for f in entry.get("files", []):
        p = f if os.path.isabs(f) else os.path.join(sd, f)
        try:
            if os.path.getsize(p) <= 0:
                return False
        except OSError:
            return False
    return True


# ---------------------------------------------------------------------------
# Self-healing: a missing/incomplete installed.json record must not read as
# "not installed" when the thing it describes actually works -- found 2026-09-12
# when a state dir built before the "audio-runtime" component existed (piper,
# kokoro-onnx, faster-whisper, numpy and soundfile all genuinely importable) had
# _component_files_ok(rec.get("audio-runtime")) always False, since there was no
# such record to check -- the banner told an existing user to re-download
# something they already had. The record is a fast path, not the truth: when it
# can't confirm a component, PROBE before concluding it's absent.
# ---------------------------------------------------------------------------

_PROBE_CACHE = {}


def _probe_import(modules):
    """Best-effort: if the state venv's python can import every module in
    `modules`, returns each module's absolute __file__ path (same order); else
    None. Never raises -- no venv, a timeout, an import error, anything at all
    just means None, the same "can't confirm it" a caller already treats as "not
    installed". Cached per-process (keyed by venv path + modules) since detect()
    can call this more than once per run and it spawns a subprocess."""
    py = venv_python()
    if not py:
        return None
    key = (py, tuple(sorted(modules)))
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]
    result = None
    try:
        code = "\n".join(f"import {m}" for m in modules) + "\n" + \
               "\n".join(f"import os; print(os.path.abspath({m}.__file__))" for m in modules)
        r = subprocess.run([py, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            timeout=10, text=True)
        if r.returncode == 0:
            paths = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
            if len(paths) == len(modules):
                result = paths
    except Exception:  # noqa: BLE001 -- a probe must never raise; "can't tell" == absent
        result = None
    _PROBE_CACHE[key] = result
    return result


def _try_repair_installed_json(updates):
    """Best-effort merge of `updates` (component key -> record dict) into
    installed.json, guarded by the same mkdir-based lock setup.sh's installer
    takes, non-blocking: a repair only makes the NEXT call fast, it is never
    required for this call to be correct, so if an install is already holding the
    lock this just skips (and tries again next time) rather than making a
    read-only `status` wait on a download. Never raises."""
    lock_dir = os.path.join(state_dir(), ".lock")
    try:
        os.mkdir(lock_dir)
    except OSError:
        return False
    try:
        path = os.path.join(state_dir(), "installed.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeDecodeError):
            data = {}
        data.update(updates)
        _atomic_write_json(path, data)
        return True
    except OSError:
        return False
    finally:
        try:
            os.rmdir(lock_dir)
        except OSError:
            pass


def _probe_model_files(subdir, filenames):
    """Absolute paths for `filenames` under models_dir()/subdir if every one exists
    and is non-empty, else None. Used alongside _probe_import() for voice-piper/
    voice-kokoro so a probe based on package-importability alone can't paper over
    the actual downloaded voice files having been deleted separately from the
    package (importable-but-no-models is a real, different, state)."""
    d = os.path.join(models_dir(), subdir)
    paths = [os.path.join(d, n) for n in filenames]
    for p in paths:
        try:
            if os.path.getsize(p) <= 0:
                return None
        except OSError:
            return None
    return paths


def _ok_or_probe(rec, key, modules, model_subdir=None, model_filenames=None):
    """_component_files_ok(rec.get(key)), with a probe-based fallback (+ best-effort
    installed.json repair) when the record is missing or stale. `model_subdir`/
    `model_filenames`, when given, are also required from disk (see
    _probe_model_files) -- used for voice-piper/voice-kokoro so the probe can't be
    fooled by an importable package whose downloaded models are gone."""
    entry = rec.get(key)
    if _component_files_ok(entry):
        return True
    import_paths = _probe_import(modules)
    if import_paths is None:
        return False
    files = list(import_paths)
    if model_subdir is not None:
        model_paths = _probe_model_files(model_subdir, model_filenames)
        if model_paths is None:
            return False
        files += model_paths
    _try_repair_installed_json({key: {"ok": True, "requires_venv": True, "healed": True, "files": files}})
    return True


def _ok_or_probe_qa_level(rec, level):
    """Like _ok_or_probe(), but qa-base/qa-small/qa-medium all share one Python
    package (faster_whisper), so "faster_whisper is importable" alone can't tell
    them apart -- this additionally requires that level's own model.bin on disk."""
    entry = rec.get(f"qa-{level}")
    if _component_files_ok(entry):
        return True
    pattern = os.path.join(models_dir(), "whisper", f"models--Systran--faster-whisper-{level}",
                            "snapshots", "*", "model.bin")
    matches = glob.glob(pattern)
    if not matches:
        return False
    try:
        model_path = os.path.realpath(matches[0])
        if os.path.getsize(model_path) <= 0:
            return False
    except OSError:
        return False
    import_paths = _probe_import(("faster_whisper",))
    if import_paths is None:
        return False
    _try_repair_installed_json({
        f"qa-{level}": {"ok": True, "requires_venv": True, "healed": True,
                         "files": [model_path] + import_paths},
    })
    return True


def _best_installed(levels, installed_pred):
    """levels: worst->best level names, NOT including 'none'. The best (last) level
    for which installed_pred is True, or None if nothing is installed."""
    for lvl in reversed(levels):
        if installed_pred(lvl):
            return lvl
    return None


def _resolve_active(levels, setting, installed_pred):
    """levels: worst->best level names, NOT including 'none'. setting: the cfg value
    ('auto', 'none', or one of `levels`). installed_pred(level) -> bool. Returns the
    active level name, or None. An explicit setting naming an installed level always
    wins; 'none' always means None; anything else (including 'auto', or a typo) falls
    back to the best installed level."""
    if setting == "none":
        return None
    if setting in levels:
        return setting if installed_pred(setting) else None
    return _best_installed(levels, installed_pred)


def _ffmpeg_detect():
    """(ffmpeg_path, ffprobe_path, source). source is "bundled" (our own
    ffmpeg-static component -- a sudo-free static download under state_dir()/bin,
    OR a `brew install ffmpeg` WE ran; either way found via installed.json, not
    guessed from a path) or "system" (found on PATH) or None if neither exists.
    Bundled always wins over PATH -- found by a real first-run report, 2026-09-12:
    a user who can't sudo shouldn't have their own working install shadowed by a
    broken/missing system one, and setup.sh's smoke test already proved the bundled
    copy runs. setup.sh always records [ffmpeg_path, ffprobe_path] in that order in
    the "ffmpeg-static" component -- see install_ffmpeg_static()."""
    entry = _installed_record().get("ffmpeg-static")
    if _component_files_ok(entry):
        files = entry.get("files", [])
        if len(files) >= 2:
            sd = state_dir()
            ffmpeg_p = files[0] if os.path.isabs(files[0]) else os.path.join(sd, files[0])
            ffprobe_p = files[1] if os.path.isabs(files[1]) else os.path.join(sd, files[1])
            return ffmpeg_p, ffprobe_p, "bundled"
    ffmpeg_p = _which("ffmpeg")
    ffprobe_p = _which("ffprobe")
    return ffmpeg_p, ffprobe_p, ("system" if ffmpeg_p else None)


def detect():
    """What is actually installed/available right now. Reads the real config (via
    load()) to resolve voice_active/qa_active against an explicit setting; callers
    that want to test format_status()/status() against a hypothetical machine should
    pass a hand-built dict of this shape straight to those functions instead of
    calling detect()."""
    cfg = load()
    rec = _installed_record()

    # Both engines need the shared audio runtime (numpy to synthesize into, soundfile
    # to write the wav) recorded by setup.sh's _ensure_audio_runtime(); a piper-tts
    # or kokoro-onnx record that's otherwise intact is still not usable if that got
    # removed independently (e.g. a stray `pip uninstall soundfile`) -- found via the
    # end-to-end stranger test, 2026-09-12: a fresh piper-only install had no
    # soundfile at all until setup.sh started installing it explicitly.
    audio_runtime_ok = _ok_or_probe(rec, "audio-runtime", ("numpy", "soundfile"))
    piper_ok = audio_runtime_ok and _ok_or_probe(
        rec, "voice-piper", ("piper",), "piper",
        ("en_US-amy-medium.onnx", "en_US-amy-medium.onnx.json",
         "en_US-ryan-high.onnx", "en_US-ryan-high.onnx.json"))
    kokoro_ok = audio_runtime_ok and _ok_or_probe(
        rec, "voice-kokoro", ("kokoro_onnx",), "kokoro",
        ("kokoro-v1.0.onnx", "voices-v1.0.bin"))
    voice_active = _resolve_active(
        VOICE_LEVELS[1:], cfg["voice_engine"],
        lambda lvl: {"piper": piper_ok, "kokoro": kokoro_ok}[lvl],
    )

    qa_models = [lvl for lvl in QA_LEVELS[1:] if _ok_or_probe_qa_level(rec, lvl)]
    qa_active = _resolve_active(QA_LEVELS[1:], cfg["qa_level"], lambda lvl: lvl in qa_models)

    sd = state_dir()
    ffmpeg_path, ffprobe_path, ffmpeg_source = _ffmpeg_detect()
    return {
        "python": ".".join(str(p) for p in sys.version_info[:3]),
        "ffmpeg": ffmpeg_path,
        "ffprobe": ffprobe_path,
        "ffmpeg_source": ffmpeg_source,  # "bundled" | "system" | None
        # Verified 2026-09-12: neither piper-tts 1.8.0 nor kokoro-onnx 0.6.1 need this
        # installed system-wide (piper embeds its own phonemization data; kokoro-onnx
        # pulls in the `espeakng-loader` wheel, which ships the shared library). Kept
        # here as a diagnostic field only -- format_status() does not gate on it.
        "espeak_ng": _which("espeak-ng", "espeak"),
        "voice": {"piper": piper_ok, "kokoro": kokoro_ok},
        "voice_active": voice_active,
        "qa": {
            # "main" was dropped deliberately: it's a generic-enough binary name
            # (Go/Rust/C build output all over the place) that treating any "main"
            # on PATH as whisper.cpp would be a false positive, not a real detection.
            "whisper_cli": _which("whisper-cli", "whisper-cpp"),
            "faster_whisper": bool(qa_models),
            "models": qa_models,
        },
        "qa_active": qa_active,
        "telegram": os.path.exists(os.path.join(_xdg_config_home(), "telegram-send", "bots.json")),
        "state_dir": sd,
        "state_dir_error": _dir_problem(sd),
        "venv": venv_python(),
    }


# ---------------------------------------------------------------------------
# auto_setup: what would be installed automatically, right now, and why
# ---------------------------------------------------------------------------

#: The only scope values `only=` accepts, besides None (no narrowing). Anything
#: else is a caller error, not a value to silently ignore -- see auto_setup_plan().
AUTO_SETUP_ONLY_VALUES = ("audio",)


def auto_setup_plan(cfg=None, det=None, only=None):
    """What auto_setup should do right now: which components are missing and
    should be installed automatically, in priority order (ffmpeg, then voice, then
    qa), and the estimated total download AND disk cost. This is the SINGLE
    source of truth for that decision -- setup.sh's `autosetup` calls
    `config.py plan` for it (via this function) rather than re-implementing the
    logic in bash, so the plan `status --json` reports and the plan actually
    executed can never drift apart.

    Respects auto_setup itself ("never" installs nothing, full stop) and each
    setting's own explicit choice: voice_engine/qa_level == "none" is skipped even
    under "always" (an explicit opt-out beats an implicit install), and an explicit
    engine/level (not "auto") is what gets installed, not always the cheapest one.
    Only fills in what's completely MISSING (voice_active/qa_active is None) --
    this is "get a stranger to a working baseline", not "upgrade piper to kokoro".

    `only="audio"` narrows scope to ffmpeg+voice for this call, same as
    `autosetup --only audio` -- except "never" always wins regardless, since
    installing nothing implicitly is the user's explicit choice, not something a
    scope flag should override.

    HIGH4 (found by review, 2026-09-12): `only` used to be compared with
    `== "audio"` and anything else silently fell through to NO narrowing at all
    -- `--only qa`, `--only voice`, even a typo like `--only Audio`, installed
    EVERYTHING (~1.1 GB), silently. `only` is now validated: None means "no
    narrowing" (the normal case), "audio" narrows, anything else raises
    ValueError rather than being quietly treated as either of those. The CLI
    (`config.py plan`, and setup.sh's `--only` parsing) catches the caller-facing
    version of this and exits 2 naming the valid values; this function raising is
    what makes that possible instead of the bad value just evaporating here.

    Returns:
      {"mode": <configured auto_setup value>,
       "effective_mode": <mode, narrowed by `only` if applicable>,
       "user_said_never": bool,
       "components": [{"component": "ffmpeg-static"|"voice-piper"|"voice-kokoro"|
                        "qa-base"|"qa-small"|"qa-medium", "kind": "ffmpeg"|"voice"|"qa",
                        "target": <engine/level name>,
                        "bytes": <int, disk footprint estimate>,
                        "download_bytes": <int, wire estimate -- smaller, sometimes
                                           much smaller, than "bytes"; see
                                           FFMPEG_DOWNLOAD_BYTES/FFMPEG_DISK_BYTES>},
                       ...],
       "total_bytes": <int, sum of "bytes">,
       "total_download_bytes": <int, sum of "download_bytes">}
    components is empty (and both totals 0) whenever there's nothing to do,
    whether because auto_setup=never or because everything needed is already
    installed -- check "user_said_never" to tell those two apart."""
    if only is not None and only not in AUTO_SETUP_ONLY_VALUES:
        raise ValueError(f"only must be one of {AUTO_SETUP_ONLY_VALUES} or None, got {only!r}")

    cfg = load() if cfg is None else cfg
    det = detect() if det is None else det

    mode = cfg.get("auto_setup", "always")
    if mode not in AUTO_SETUP_LEVELS:
        mode = "always"
    effective_mode = "audio-only" if (only == "audio" and mode == "always") else mode

    result = {"mode": mode, "effective_mode": effective_mode,
              "user_said_never": mode == "never", "components": [],
              "total_bytes": 0, "total_download_bytes": 0}
    if effective_mode == "never":
        return result

    def add(component, kind, target, disk_bytes, download_bytes):
        result["components"].append({"component": component, "kind": kind, "target": target,
                                      "bytes": disk_bytes, "download_bytes": download_bytes})
        result["total_bytes"] += disk_bytes
        result["total_download_bytes"] += download_bytes

    if not det.get("ffmpeg"):
        add("ffmpeg-static", "ffmpeg", "ffmpeg", FFMPEG_DISK_BYTES, FFMPEG_DOWNLOAD_BYTES)

    voice_engine = cfg.get("voice_engine", "auto")
    if voice_is_downgraded(cfg, det):
        # An upgrade, not a gap: piper already renders, so this never blocks an
        # episode. It downloads alongside the research, and because `auto` resolves
        # to the best INSTALLED engine at render time, the very next render picks
        # kokoro up if it finished -- and quietly stays on piper if it didn't.
        result["components"].append({
            "component": "voice-kokoro", "kind": "voice", "target": "kokoro",
            "upgrade_from": "piper",
            "bytes": VOICE_DISK_BYTES["kokoro"], "download_bytes": VOICE_DOWNLOAD_BYTES["kokoro"],
        })
        result["total_bytes"] += VOICE_DISK_BYTES["kokoro"]
        result["total_download_bytes"] += VOICE_DOWNLOAD_BYTES["kokoro"]
    elif det.get("voice_active") is None and voice_engine != "none":
        # Under "auto" we install the BEST engine, not the smallest. Found on a real
        # machine, 2026-09-12: a fresh install auto-installed piper, voice_engine=auto
        # then resolved to it as "best installed" forever, and the owner heard the
        # drop (22.05 kHz en_US-amy-medium vs kokoro's 24 kHz af_heart) across two
        # episodes without anything in the banner hinting a better engine existed.
        # The difference is ~160 MB on a download the user is already waiting through;
        # a wrong-sounding episode is the more expensive mistake. `piper` stays a
        # first-class explicit choice for anyone who wants small and fast.
        target = voice_engine if voice_engine in VOICE_LEVELS[1:] else "kokoro"
        add(f"voice-{target}", "voice", target,
            VOICE_DISK_BYTES.get(target, VOICE_DISK_BYTES["kokoro"]),
            VOICE_DOWNLOAD_BYTES.get(target, VOICE_DOWNLOAD_BYTES["kokoro"]))

    if effective_mode == "always":
        qa_level = cfg.get("qa_level", "auto")
        if det.get("qa_active") is None and qa_level != "none":
            target = qa_level if qa_level in QA_LEVELS[1:] else "base"
            add(f"qa-{target}", "qa", target,
                QA_DISK_BYTES.get(target, QA_DISK_BYTES["base"]),
                QA_DOWNLOAD_BYTES.get(target, QA_DOWNLOAD_BYTES["base"]))

    return result


# ---------------------------------------------------------------------------
# Status: machine-readable + human banner
# ---------------------------------------------------------------------------

def voice_is_downgraded(cfg, det):
    """True when this machine is rendering with piper while kokoro -- the engine
    `auto` is supposed to give people -- is not installed.

    Only ever true under voice_engine=auto: someone who typed `piper` chose small
    and fast and is not second-guessed. This exists because 0.1.2 auto-installed
    piper under `auto`, and `auto` then resolved to it as "best installed" forever;
    the machines that hit that window keep sounding worse than they should until
    something notices, so both the planner and the banner ask this question."""
    if cfg.get("voice_engine", "auto") != "auto":
        return False
    if det.get("voice_active") != "piper":
        return False
    return not (det.get("voice", {}) or {}).get("kokoro", False)


def _upgrade_voice_note():
    return ('Say "upgrade voice" to add audio -- piper ({}, fast) or kokoro ({}, best quality).'
            .format(VOICE_SIZE_HINTS["piper"], VOICE_SIZE_HINTS["kokoro"]))


def _tier_row(*, active, setting, levels, installed_pred, size_hints,
              active_note, off_note_verb, upgrade_note):
    """Shared shape for the voice/qa status rows. `active`: det[...]['*_active'], the
    already-resolved level (or None). `setting`: the raw cfg value ('auto', 'none',
    or an explicit level). `installed_pred(level)->bool`. Distinguishes four cases
    so the banner never says something that isn't true:
      1. active                      -> state=<level>, `active_note`
      2. setting == 'none'           -> "off (by choice)", not "not installed"
      3. setting names a level that
         isn't installed             -> "requested <level> (not installed)",
                                          naming what IS available (if anything) and
                                          the real size of the level actually missing
      4. otherwise (auto, nothing
         installed)                  -> "not installed", generic upgrade note
    """
    if active:
        return {"active": active, "state": active, "note": active_note(active)}
    if setting == "none":
        return {"active": None, "state": "off (by choice)", "note": upgrade_note()}
    if setting in levels:
        best = _best_installed(levels, installed_pred)
        size = size_hints.get(setting, "")
        if best:
            note = (f'{best} is installed and available now. Say "upgrade {off_note_verb}" '
                     f'for {setting} ({size}).')
        else:
            note = f'Say "upgrade {off_note_verb}" to install {setting} ({size}).'
        return {"active": None, "state": f"requested {setting} (not installed)", "note": note}
    return {"active": None, "state": "not installed", "note": upgrade_note()}


def status(cfg=None, det=None):
    """Machine-readable tier + upgrade info. Pure function of the cfg/det passed in
    (or the real load()/detect() if omitted) -- never re-derives them itself, so a
    caller (e.g. --selftest) can hand it a hypothetical `det` shape.

    `cfg` (when not passed in) is load()'s resolution: DEFAULTS -> plugin
    install-time options -> our own config file -> environment, highest wins --
    see the module docstring and load()."""
    cfg = load() if cfg is None else cfg
    det = detect() if det is None else det

    ffmpeg_ok = bool(det.get("ffmpeg"))
    voice_installed = det.get("voice", {}) or {}
    qa_models = det.get("qa", {}).get("models", []) or []

    downgraded = voice_is_downgraded(cfg, det)

    def voice_active_note(level):
        if ffmpeg_ok:
            if downgraded:
                return ('Audio will be generated -- but piper sounds noticeably thinner than '
                        'kokoro ({}), which is what "auto" installs now. Say "upgrade voice" '
                        '(or let auto_setup fetch it on the next episode).'
                        .format(VOICE_SIZE_HINTS["kokoro"]))
            return "Audio will be generated."
        # HIGH: never claim audio works when the one tool that produces the final
        # file is missing -- the ffmpeg warning below still fires separately.
        return f"{level} is installed, but ffmpeg is missing -- no audio until it's " \
               f"installed (see ffmpeg below)."

    voice = _tier_row(
        active=det.get("voice_active"), setting=cfg.get("voice_engine", "auto"),
        levels=VOICE_LEVELS[1:], installed_pred=lambda lvl: voice_installed.get(lvl, False),
        size_hints=VOICE_SIZE_HINTS, active_note=voice_active_note,
        off_note_verb="voice", upgrade_note=_upgrade_voice_note,
    )

    qa = _tier_row(
        active=det.get("qa_active"), setting=cfg.get("qa_level", "auto"),
        levels=QA_LEVELS[1:], installed_pred=lambda lvl: lvl in qa_models,
        size_hints=QA_SIZE_HINTS, active_note=lambda level: "Rendered audio will be checked against the script.",
        off_note_verb="qa",
        upgrade_note=lambda: f'Say "upgrade qa" to check audio against the script ({QA_SIZE_HINTS["base"]}).',
    )

    telegram_bot = cfg.get("telegram_bot") or ""
    if telegram_bot:
        if det.get("telegram"):
            delivery = {"mode": "telegram", "state": f"telegram ({telegram_bot})",
                        "note": "Episodes will be sent to Telegram."}
        else:
            delivery = {"mode": "telegram", "state": f"telegram ({telegram_bot}) -- bots.json missing",
                        "note": "Create ~/.config/telegram-send/bots.json, or clear telegram_bot "
                                "to fall back to local files."}
    else:
        delivery = {"mode": "local", "state": f"local file ({cfg.get('episodes_dir')})",
                    "note": 'Say "configure telegram" to send episodes to Telegram.'}

    # ffmpeg: always shown (not just when missing), so a user can tell a bundled
    # (sudo-free, our own state dir) copy from a system one -- found by a real
    # first-run report, 2026-09-12: the old banner only spoke up when ffmpeg was
    # missing, and even then just pointed at `sudo`, which the user couldn't run.
    ffmpeg_source = det.get("ffmpeg_source")
    if ffmpeg_ok:
        ffmpeg_row = {"state": ffmpeg_source or "found", "path": det.get("ffmpeg"),
                      "note": f"{det.get('ffmpeg')} ({ffmpeg_source})."}
    else:
        ffmpeg_row = {
            "state": "missing", "path": None,
            "note": f'Say "install ffmpeg" for a sudo-free static build (~{FFMPEG_DOWNLOAD_BYTES // 1_000_000} MB '
                     f'download, ~{FFMPEG_DISK_BYTES // 1_000_000} MB on disk, no admin needed) -- or, if you '
                     'have it: brew install ffmpeg | sudo apt install ffmpeg.',
        }

    warnings = []
    if not ffmpeg_ok:
        warnings.append({
            "component": "ffmpeg",
            "message": "missing -- required for audio.",
            "fix": "setup.sh install ffmpeg-static --yes   (no sudo) | brew install ffmpeg | sudo apt install ffmpeg",
        })
    state_dir_error = det.get("state_dir_error")
    if state_dir_error:
        warnings.append({
            "component": "state dir",
            "message": f"{det.get('state_dir')} is not usable ({state_dir_error}).",
            "fix": "set PODCAST_STATE_DIR to a writable directory, e.g. "
                   "export PODCAST_STATE_DIR=~/.topic-podcast",
        })

    # auto_setup: what the skill needs to decide whether/what to fetch in the
    # background before rendering an episode -- what's missing, the estimated
    # total download, and whether the user has already said "never" (in which case
    # the skill must not fetch anything without being asked).
    plan = auto_setup_plan(cfg, det)
    auto_setup_info = {
        "mode": plan["mode"],
        "user_said_never": plan["user_said_never"],
        # "missing" is a gap (no audio at all without it); "upgrades" is something
        # that already works but shouldn't stay -- the skill words the two
        # differently and must never block an episode on an upgrade.
        "missing": [c["component"] for c in plan["components"] if not c.get("upgrade_from")],
        "upgrades": [c["component"] for c in plan["components"] if c.get("upgrade_from")],
        "total_bytes": plan["total_bytes"],
    }

    return {"voice": voice, "qa": qa, "voice_downgraded": downgraded,
            # The resolved settings themselves. SKILL.md has always told the skill to
            # read episodes_dir from `status --json`, and until now the key wasn't
            # there -- only a formatted copy inside delivery.state. Everything a
            # caller needs to start an episode is here, already resolved through
            # DEFAULTS -> plugin options -> config file -> environment.
            "config": {k: cfg.get(k, DEFAULTS.get(k)) for k in DEFAULTS},
            "delivery": delivery, "ffmpeg": ffmpeg_row,
            "auto_setup": auto_setup_info, "warnings": warnings, "ok": not warnings}


def format_status(cfg=None, det=None):
    """Short, plain, human banner -- what's active and exactly what to say to upgrade."""
    s = status(cfg, det)

    def row(label, state_text, note):
        left = f"{label + ':':<11}{state_text}"
        return f"{left:<42} {note}" if note else left

    v = s["voice"]
    v_state = v["state"] if not v["active"] else f'{v["state"]} ({VOICE_LABELS.get(v["active"], "")})'
    lines = [row("Voice", v_state, v["note"])]

    q = s["qa"]
    lines.append(row("QA", q["state"], q["note"]))

    d = s["delivery"]
    lines.append(row("Delivery", d["state"], d["note"]))

    f = s["ffmpeg"]
    lines.append(row("ffmpeg", f["state"], f["note"]))

    for w in s["warnings"]:
        if w["component"] == "ffmpeg":
            continue  # already shown via the dedicated ffmpeg row above
        lines.append(row(w["component"], w["message"], f"Install: {w['fix']}"))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def run_selftest():
    import contextlib
    import io
    import tempfile

    ok = [True]

    def check(name, cond):
        print(("PASS" if cond else "FAIL") + f"  {name}")
        if not cond:
            ok[0] = False

    tracked_env = list(ENV_OVERRIDES) + [
        "PODCAST_CONFIG", "PODCAST_STATE_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
        "CLAUDE_CONFIG_DIR",
    ]
    saved = {k: os.environ.get(k) for k in tracked_env}

    def restore_env():
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    try:
        for k in tracked_env:
            os.environ.pop(k, None)

        with tempfile.TemporaryDirectory() as td:
            cfg_path = os.path.join(td, "config.json")
            state_path = os.path.join(td, "state")
            os.environ["PODCAST_CONFIG"] = cfg_path

            # -- resolution order: defaults --
            cfg = load()
            check("defaults: episodes_dir", cfg["episodes_dir"] == os.path.expanduser(DEFAULTS["episodes_dir"]))
            check("defaults: voice_engine", cfg["voice_engine"] == "auto")
            check("defaults: default_cast", cfg["default_cast"] == "two-host")
            check("defaults: qa_level", cfg["qa_level"] == "auto")
            check("defaults: telegram_bot empty", cfg["telegram_bot"] == "")
            check("config_path() honors PODCAST_CONFIG", config_path() == cfg_path)

            # -- resolution order: plugin install-time options override defaults,
            # but our own config file (and env) still override THEM -- found by a
            # full stranger validation, 2026-09-12: Claude Code stores userConfig
            # install answers in its own settings files (pluginConfigs), never as
            # env vars outside a hook, so config.py has to go read them itself. --
            prev_cwd = os.getcwd()
            claude_home = os.path.join(td, "claude-home")
            os.makedirs(claude_home, exist_ok=True)
            os.environ["CLAUDE_CONFIG_DIR"] = claude_home
            os.chdir(td)  # no .claude/ here -- isolates from the real project's cwd
            try:
                def write_settings(options, marketplace="podcast-skill"):
                    with open(os.path.join(claude_home, "settings.json"), "w", encoding="utf-8") as f:
                        json.dump({"pluginConfigs": {f"podcast@{marketplace}": {"options": options}}}, f)

                write_settings({"episodes_dir": "/tmp/EPISODES_PROBE", "voice_engine": "piper"})
                cfg = load()
                check("plugin option overrides default (episodes_dir)",
                      cfg["episodes_dir"] == os.path.abspath("/tmp/EPISODES_PROBE"))
                check("plugin option overrides default (voice_engine)", cfg["voice_engine"] == "piper")

                # PODCAST_* env still wins over a plugin option.
                os.environ["PODCAST_EPISODES_DIR"] = "/tmp/EPISODES_ENV_WINS"
                check("env overrides plugin option",
                      load()["episodes_dir"] == os.path.abspath("/tmp/EPISODES_ENV_WINS"))
                del os.environ["PODCAST_EPISODES_DIR"]

                # our own config file still wins over a plugin option (no env involved).
                _atomic_write_json(cfg_path, {"voice_engine": "kokoro"})
                check("our own config file overrides plugin option",
                      load()["voice_engine"] == "kokoro")
                os.remove(cfg_path)

                # a differently-named marketplace is still matched by prefix.
                write_settings({"qa_level": "small"}, marketplace="some-other-fork")
                check("differently-named marketplace (podcast@some-other-fork) still matched",
                      load()["qa_level"] == "small")

                # unknown key ignored, invalid enum value warns and falls back, exactly
                # like an invalid env var does.
                write_settings({"qa_level": "extreme", "bogus_option": "x"})
                stderr_buf = io.StringIO()
                with contextlib.redirect_stderr(stderr_buf):
                    cfg = load()
                check("plugin option: unknown key ignored", "bogus_option" not in cfg)
                check("plugin option: invalid enum value rejected, not adopted", cfg["qa_level"] != "extreme")
                check("plugin option: invalid enum value falls back to default", cfg["qa_level"] == "auto")
                check("plugin option: invalid enum value warns", "extreme" in stderr_buf.getvalue())

                # a malformed settings.json (bad JSON) is a silent skip, not a crash.
                with open(os.path.join(claude_home, "settings.json"), "w", encoding="utf-8") as f:
                    f.write("{not valid json")
                try:
                    cfg = load()
                    check("malformed Claude settings.json falls back to defaults, no crash",
                          cfg["voice_engine"] == "auto")
                except Exception as e:  # noqa: BLE001
                    check(f"malformed Claude settings.json falls back to defaults, no crash (raised {e!r})", False)

                # pluginConfigs present but the wrong shape (list instead of object,
                # entry missing "options", options not an object) must not crash either.
                for bad_shape, label in (
                    ({"pluginConfigs": ["not", "a", "dict"]}, "pluginConfigs not an object"),
                    ({"pluginConfigs": {"podcast@x": "not-a-dict"}}, "entry not an object"),
                    ({"pluginConfigs": {"podcast@x": {"options": "not-a-dict"}}}, "options not an object"),
                ):
                    with open(os.path.join(claude_home, "settings.json"), "w", encoding="utf-8") as f:
                        json.dump(bad_shape, f)
                    try:
                        cfg = load()
                        check(f"malformed pluginConfigs shape tolerated: {label}", cfg["voice_engine"] == "auto")
                    except Exception as e:  # noqa: BLE001
                        check(f"malformed pluginConfigs shape tolerated: {label} (raised {e!r})", False)

                # project-local settings (.claude/settings.local.json under cwd) are
                # also checked, and outrank the user-level Claude settings file.
                os.remove(os.path.join(claude_home, "settings.json"))
                os.makedirs(os.path.join(td, ".claude"), exist_ok=True)
                with open(os.path.join(td, ".claude", "settings.local.json"), "w", encoding="utf-8") as f:
                    json.dump({"pluginConfigs": {"podcast@podcast-skill": {"options": {"voice_engine": "kokoro"}}}}, f)
                check("project-local .claude/settings.local.json is also checked",
                      load()["voice_engine"] == "kokoro")
                os.remove(os.path.join(td, ".claude", "settings.local.json"))
            finally:
                os.chdir(prev_cwd)
                del os.environ["CLAUDE_CONFIG_DIR"]

            # -- resolution order: config file overrides defaults --
            _atomic_write_json(cfg_path, {"voice_engine": "piper", "qa_level": "base"})
            cfg = load()
            check("file overrides default (voice_engine)", cfg["voice_engine"] == "piper")
            check("file overrides default (qa_level)", cfg["qa_level"] == "base")
            check("file leaves untouched defaults alone", cfg["telegram_bot"] == "")

            # -- resolution order: env overrides file --
            os.environ["PODCAST_VOICE_ENGINE"] = "kokoro"
            cfg = load()
            check("env overrides file (voice_engine)", cfg["voice_engine"] == "kokoro")
            os.environ["PODCAST_DEFAULT_CAST"] = "panel"
            try:
                check("env overrides default (default_cast)", load()["default_cast"] == "panel")
            finally:
                del os.environ["PODCAST_DEFAULT_CAST"]
            check("env leaves other file keys alone (qa_level)", cfg["qa_level"] == "base")
            os.environ["PODCAST_VOICE_ENGINE"] = ""
            cfg = load()
            check("empty env var does NOT override file", cfg["voice_engine"] == "piper")
            del os.environ["PODCAST_VOICE_ENGINE"]

            # -- save() round-trip --
            new_cfg = save({"telegram_bot": "mybot", "unknown_key": "x"})
            check("save() persists a known key", new_cfg["telegram_bot"] == "mybot")
            check("save() ignores an unknown key", "unknown_key" not in new_cfg)
            check("save() preserves earlier keys", new_cfg["voice_engine"] == "piper")
            check("save() round-trip visible to a fresh load()", load()["telegram_bot"] == "mybot")

            # -- malformed / missing config file: fall back to defaults, never raise --
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write("{not valid json")
            cfg = load()
            check("malformed config file falls back to defaults", cfg["voice_engine"] == "auto")
            os.remove(cfg_path)
            cfg = load()
            check("missing config file falls back to defaults", cfg["qa_level"] == "auto")

            # -- state dir / models dir / venv_python --
            os.environ["PODCAST_STATE_DIR"] = state_path
            check("state_dir() honors PODCAST_STATE_DIR", state_dir() == state_path)
            check("state_dir() creates the directory", os.path.isdir(state_path))
            md = models_dir()
            check("models_dir() nests under state_dir()", md == os.path.join(state_path, "models"))
            check("models_dir() creates the directory", os.path.isdir(md))
            check("venv_python() is None before the venv exists", venv_python() is None)
            venv_bin = os.path.join(state_path, "venv", "bin")
            os.makedirs(venv_bin, exist_ok=True)
            open(os.path.join(venv_bin, "python3"), "w", encoding="utf-8").close()
            check("venv_python() finds it once created", venv_python() == os.path.join(venv_bin, "python3"))
            del os.environ["PODCAST_STATE_DIR"]

            # -- format_status() over injected detect() shapes (fully offline) --
            base_cfg = dict(DEFAULTS)

            def shape(**kw):
                d = {"ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe", "espeak_ng": None,
                     "voice": {"piper": False, "kokoro": False}, "voice_active": None,
                     "qa": {"whisper_cli": None, "faster_whisper": False, "models": []},
                     "qa_active": None, "telegram": False, "state_dir": state_path, "venv": None}
                d.update(kw)
                return d

            nothing = shape()
            piper_base = shape(voice={"piper": True, "kokoro": False}, voice_active="piper",
                                qa={"whisper_cli": None, "faster_whisper": True, "models": ["base"]},
                                qa_active="base")
            kokoro_medium = shape(voice={"piper": True, "kokoro": True}, voice_active="kokoro",
                                   espeak_ng="/usr/bin/espeak-ng",
                                   qa={"whisper_cli": "/usr/local/bin/whisper-cli", "faster_whisper": True,
                                       "models": ["base", "small", "medium"]},
                                   qa_active="medium")
            no_ffmpeg = shape(ffmpeg=None, ffprobe=None)

            for name, det in (("nothing installed", nothing), ("piper + qa base", piper_base),
                               ("kokoro + qa medium", kokoro_medium), ("ffmpeg missing", no_ffmpeg)):
                try:
                    out = format_status(base_cfg, det)
                    check(f"format_status() runs: {name}", isinstance(out, str) and len(out) > 0)
                except Exception as e:  # noqa: BLE001 -- selftest wants a PASS/FAIL, not a traceback
                    check(f"format_status() runs: {name} (raised {e!r})", False)

            check("format_status(): upgrade hint when nothing installed",
                  "upgrade" in format_status(base_cfg, nothing).lower())
            check("format_status(): shows active voice engine",
                  "piper" in format_status(base_cfg, piper_base))
            check("format_status(): shows best-quality label for kokoro",
                  "kokoro" in format_status(base_cfg, kokoro_medium)
                  and "best quality" in format_status(base_cfg, kokoro_medium))
            check("format_status(): shows active qa level",
                  "medium" in format_status(base_cfg, kokoro_medium))
            out_no_ffmpeg = format_status(base_cfg, no_ffmpeg)
            check("format_status(): warns when ffmpeg missing",
                  "ffmpeg" in out_no_ffmpeg.lower() and "install" in out_no_ffmpeg.lower())
            telegram_cfg = dict(base_cfg, telegram_bot="mybot")
            out_tg = format_status(telegram_cfg, shape(telegram=True))
            check("format_status(): reflects telegram delivery when configured + available",
                  "telegram" in out_tg.lower() and "mybot" in out_tg)
            out_tg_missing = format_status(telegram_cfg, shape(telegram=False))
            check("format_status(): flags telegram configured but bots.json missing",
                  "missing" in out_tg_missing.lower())

            # -- status()['ok'] tracks whether there are any warnings --
            check("status(): ok=True with nothing wrong (voice/qa aside)",
                  status(base_cfg, piper_base)["ok"] is True)
            check("status(): ok=False when ffmpeg missing",
                  status(base_cfg, no_ffmpeg)["ok"] is False)

            # -- HIGH: the banner must never promise audio when ffmpeg is missing,
            # even though a voice engine IS installed and active --
            kokoro_no_ffmpeg = shape(voice={"piper": False, "kokoro": True}, voice_active="kokoro",
                                      ffmpeg=None, ffprobe=None)
            out = format_status(base_cfg, kokoro_no_ffmpeg)
            check("HIGH4: voice row does not promise audio when ffmpeg is missing",
                  "will be generated" not in out.lower())
            check("HIGH4: voice row still names the installed engine",
                  "kokoro" in status(base_cfg, kokoro_no_ffmpeg)["voice"]["state"])
            check("HIGH4: voice row explains ffmpeg is the blocker",
                  "ffmpeg" in status(base_cfg, kokoro_no_ffmpeg)["voice"]["note"].lower())

            # -- MED5: an explicit request for a level that isn't installed must name
            # what IS available and quote the size of the level actually missing,
            # not silently read as "not installed" with base's size --
            qa_medium_wanted_base_installed = shape(
                qa={"whisper_cli": None, "faster_whisper": True, "models": ["base"]}, qa_active=None)
            qa_cfg = dict(base_cfg, qa_level="medium")
            qa_row = status(qa_cfg, qa_medium_wanted_base_installed)["qa"]
            check("MED5: state names the unmet explicit request", "medium" in qa_row["state"])
            check("MED5: state/note says it's not installed", "not installed" in qa_row["state"])
            check("MED5: note says what IS available now", "base" in qa_row["note"])
            check("MED5: note quotes medium's size, not base's",
                  QA_SIZE_HINTS["medium"] in qa_row["note"] and QA_SIZE_HINTS["base"] not in qa_row["note"])

            # -- MED6: voice_engine=none / qa_level=none is a choice, not an absence --
            none_cfg = dict(base_cfg, voice_engine="none", qa_level="none")
            off_status = status(none_cfg, nothing)
            check("MED6: voice_engine=none reads as a choice", off_status["voice"]["state"] == "off (by choice)")
            check("MED6: qa_level=none reads as a choice", off_status["qa"]["state"] == "off (by choice)")
            check("MED6: 'off (by choice)' is not 'not installed'",
                  "not installed" not in off_status["voice"]["state"]
                  and "not installed" not in off_status["qa"]["state"])

            # -- MED10: an invalid env value is validated like `set` is, warns, and
            # does NOT silently fall through to a different engine --
            _atomic_write_json(cfg_path, {"voice_engine": "piper"})  # a known prior value to fall back to
            os.environ["PODCAST_VOICE_ENGINE"] = "pipr"  # typo for "piper"
            stderr_buf = io.StringIO()
            with contextlib.redirect_stderr(stderr_buf):
                cfg_bad_env = load()
            check("MED10: invalid env value is rejected, not adopted", cfg_bad_env["voice_engine"] != "pipr")
            check("MED10: invalid env value falls back to the prior resolved value (file/default)",
                  cfg_bad_env["voice_engine"] == "piper")
            check("MED10: invalid env value prints a warning", "pipr" in stderr_buf.getvalue())
            del os.environ["PODCAST_VOICE_ENGINE"]

            # -- LOW: a config path with no directory component must not crash --
            prev_cwd = os.getcwd()
            os.chdir(td)
            try:
                os.environ["PODCAST_CONFIG"] = "bare-config.json"
                try:
                    bare_cfg = save({"telegram_bot": "x"})
                    check("LOW: bare (dirless) PODCAST_CONFIG doesn't crash save()", bare_cfg["telegram_bot"] == "x")
                    check("LOW: bare PODCAST_CONFIG file actually created", os.path.exists("bare-config.json"))
                except Exception as e:  # noqa: BLE001
                    check(f"LOW: bare (dirless) PODCAST_CONFIG doesn't crash save() (raised {e!r})", False)
            finally:
                os.chdir(prev_cwd)
                os.environ["PODCAST_CONFIG"] = cfg_path

            # -- LOW: a relative episodes_dir is abspath'd, not left relative --
            save({"episodes_dir": "relative-episodes"})
            check("LOW: relative episodes_dir is absolute after load()", os.path.isabs(load()["episodes_dir"]))
            save({"episodes_dir": DEFAULTS["episodes_dir"]})

            # -- LOW: telegram detection honors XDG_CONFIG_HOME, not a hardcoded ~/.config --
            xdg_home = os.path.join(td, "xdg-config")
            os.makedirs(os.path.join(xdg_home, "telegram-send"), exist_ok=True)
            with open(os.path.join(xdg_home, "telegram-send", "bots.json"), "w", encoding="utf-8") as f:
                f.write("{}")
            os.environ["XDG_CONFIG_HOME"] = xdg_home
            check("LOW: telegram detection honors XDG_CONFIG_HOME", detect()["telegram"] is True)
            del os.environ["XDG_CONFIG_HOME"]

            # -- LOW: a generically-named "main" binary on PATH must not be mistaken
            # for whisper.cpp --
            fake_bin_dir = os.path.join(td, "fakebin")
            os.makedirs(fake_bin_dir, exist_ok=True)
            fake_main = os.path.join(fake_bin_dir, "main")
            with open(fake_main, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(fake_main, 0o755)
            prev_path = os.environ.get("PATH", "")
            os.environ["PATH"] = fake_bin_dir + os.pathsep + prev_path
            try:
                check("LOW: a bare 'main' on PATH is not reported as whisper_cli", detect()["qa"]["whisper_cli"] is None)
            finally:
                os.environ["PATH"] = prev_path

            # -- MED9: an unwritable/blocked state dir must not crash detect()/status(),
            # it must be surfaced as a warning --
            blocked_state = os.path.join(td, "blocked-state")
            with open(blocked_state, "w", encoding="utf-8") as f:
                f.write("i am a file occupying the path a directory needs")
            os.environ["PODCAST_STATE_DIR"] = blocked_state
            try:
                det_blocked = detect()
                check("MED9: detect() does not raise when the state dir path is blocked", True)
            except Exception as e:  # noqa: BLE001
                check(f"MED9: detect() does not raise when the state dir path is blocked (raised {e!r})", False)
                det_blocked = None
            if det_blocked is not None:
                check("MED9: detect() records the state dir problem", bool(det_blocked.get("state_dir_error")))
                out_blocked = format_status(base_cfg, det_blocked)
                check("MED9: format_status() surfaces the state dir problem instead of crashing",
                      "state dir" in out_blocked.lower())
            del os.environ["PODCAST_STATE_DIR"]

            # -- HIGH1: a component must not read as installed once the thing that
            # makes it RUN (the venv) is gone, even though its recorded files (e.g. a
            # model already on disk) are untouched. Also: a package-owned file (e.g.
            # venv/bin/piper, removed by `pip uninstall`) failing must flip it too,
            # even with the venv itself still present. --
            state3 = os.path.join(td, "state3")
            os.environ["PODCAST_STATE_DIR"] = state3
            try:
                model_file = os.path.join(state3, "models", "piper", "voice.onnx")
                os.makedirs(os.path.dirname(model_file), exist_ok=True)
                with open(model_file, "w", encoding="utf-8") as f:
                    f.write("x")
                piper_bin = os.path.join(state3, "venv", "bin", "piper")
                os.makedirs(os.path.dirname(piper_bin), exist_ok=True)
                with open(piper_bin, "w", encoding="utf-8") as f:
                    f.write("x")
                installed_json = os.path.join(state3, "installed.json")
                _atomic_write_json(installed_json, {
                    "voice-piper": {
                        "ok": True, "requires_venv": True,
                        "files": ["models/piper/voice.onnx", "venv/bin/piper"],
                    },
                })
                check("HIGH1: files present but no venv/bin/python3 -> NOT reported installed",
                      _component_files_ok(_installed_record().get("voice-piper")) is False)

                venv_py = os.path.join(state3, "venv", "bin", "python3")
                with open(venv_py, "w", encoding="utf-8") as f:
                    f.write("x")
                check("HIGH1: venv present + all recorded files present -> reported installed",
                      _component_files_ok(_installed_record().get("voice-piper")) is True)

                os.remove(venv_py)
                check("HIGH1: deleting the venv flips it back to NOT installed",
                      _component_files_ok(_installed_record().get("voice-piper")) is False)

                with open(venv_py, "w", encoding="utf-8") as f:
                    f.write("x")
                os.remove(piper_bin)
                check("HIGH1: venv intact but the package's own binary is gone "
                      "(pip uninstall) -> NOT installed",
                      _component_files_ok(_installed_record().get("voice-piper")) is False)

                # -- audio runtime gate (found by the end-to-end stranger test,
                # 2026-09-12): a fresh piper-only install produced numpy +
                # onnxruntime + piper-tts but NO soundfile, so render.py couldn't
                # run at all. setup.sh now installs numpy+soundfile explicitly as
                # their own "audio-runtime" component; detect() must refuse to call
                # piper (or kokoro) usable without it, even if voice-piper's own
                # record is otherwise intact. --
                with open(piper_bin, "w", encoding="utf-8") as f:
                    f.write("x")
                _atomic_write_json(installed_json, {
                    "voice-piper": {"ok": True, "requires_venv": True,
                                     "files": ["models/piper/voice.onnx", "venv/bin/piper"]},
                })
                _atomic_write_json(cfg_path, {"voice_engine": "piper"})
                det_no_audio = detect()
                check("AUDIO-RUNTIME: voice-piper recorded ok but no audio-runtime "
                      "component -> detect() reports it NOT usable",
                      det_no_audio["voice"]["piper"] is False and det_no_audio["voice_active"] is None)

                numpy_pkg = os.path.join(state3, "venv", "lib", "numpy", "__init__.py")
                os.makedirs(os.path.dirname(numpy_pkg), exist_ok=True)
                with open(numpy_pkg, "w", encoding="utf-8") as f:
                    f.write("x")
                _atomic_write_json(installed_json, {
                    "voice-piper": {"ok": True, "requires_venv": True,
                                     "files": ["models/piper/voice.onnx", "venv/bin/piper"]},
                    "audio-runtime": {"ok": True, "requires_venv": True, "files": [numpy_pkg]},
                })
                det_with_audio = detect()
                check("AUDIO-RUNTIME: voice-piper + audio-runtime both present -> usable",
                      det_with_audio["voice"]["piper"] is True and det_with_audio["voice_active"] == "piper")
            finally:
                del os.environ["PODCAST_STATE_DIR"]

            # -- SELF-HEAL: the mirror-image bug (found 2026-09-12) -- a state dir
            # built before "audio-runtime" existed as a tracked component (or before
            # any component existed) has a genuinely working venv but an
            # incomplete/absent installed.json record. detect() must probe rather
            # than trust the record's silence, and repair it so the next call is
            # fast. Faked here (a real subprocess/venv would defeat the point of an
            # offline selftest): venv_python() and subprocess.run() are monkeypatched
            # module-globally for the duration of this block only. --
            state4 = os.path.join(td, "state4")
            os.environ["PODCAST_STATE_DIR"] = state4
            os.makedirs(os.path.join(state4, "venv", "bin"), exist_ok=True)
            with open(os.path.join(state4, "venv", "bin", "python3"), "w", encoding="utf-8") as f:
                f.write("x")  # just needs to exist -- real execution is faked below

            real_venv_python = globals()["venv_python"]
            real_subprocess = globals()["subprocess"]

            class _FakeCompleted:
                def __init__(self, returncode, stdout):
                    self.returncode = returncode
                    self.stdout = stdout

            class _FakeSubprocess:
                PIPE = real_subprocess.PIPE
                DEVNULL = real_subprocess.DEVNULL

                @staticmethod
                def run(cmd, **kwargs):
                    # cmd = [py, "-c", code]; the fake "importable" set below decides
                    # success/failure per module instead of actually executing python.
                    # The "__file__" paths are touched into real (if empty of real
                    # content) existence under state4 -- a real interpreter's
                    # __file__ always resolves to a real file, and the repaired
                    # record's fast path (_component_files_ok) needs that to hold
                    # here too, not just the probe path.
                    code = cmd[2]
                    # Only the plain "import X" lines name a probed module -- the
                    # "import os; print(...)" lines also start with "import " but
                    # must not be mistaken for one.
                    modules = [ln.split()[1] for ln in code.splitlines()
                               if ln.startswith("import ") and ";" not in ln]
                    if not set(modules) <= _FAKE_IMPORTABLE:
                        return _FakeCompleted(1, "")
                    lines = []
                    for m in modules:
                        p = os.path.join(state4, "venv", "lib", "fake-pkgs", m, "__init__.py")
                        os.makedirs(os.path.dirname(p), exist_ok=True)
                        with open(p, "w", encoding="utf-8") as f:
                            f.write("x")
                        lines.append(p)
                    return _FakeCompleted(0, "\n".join(lines) + "\n")

            _FAKE_IMPORTABLE = {"numpy", "soundfile", "piper", "kokoro_onnx", "faster_whisper"}
            globals()["venv_python"] = lambda: os.path.join(state4, "venv", "bin", "python3")
            globals()["subprocess"] = _FakeSubprocess
            _PROBE_CACHE.clear()
            try:
                # 1. installed.json doesn't exist at all (nothing ever recorded) --
                # a fully "invisible" upgrade scenario, worse than the real bug.
                check("SELF-HEAL: no installed.json at all, but everything importable "
                      "-> audio-runtime probed present", _ok_or_probe({}, "audio-runtime", ("numpy", "soundfile")))

                # 2. the real bug: voice-piper/voice-kokoro/qa-base ARE recorded and
                # their files genuinely exist, but "audio-runtime" was never
                # recorded (predates that component) -- must not read as absent.
                for name, files in (
                    ("amy_onnx", "models/piper/en_US-amy-medium.onnx"),
                    ("amy_json", "models/piper/en_US-amy-medium.onnx.json"),
                    ("ryan_onnx", "models/piper/en_US-ryan-high.onnx"),
                    ("ryan_json", "models/piper/en_US-ryan-high.onnx.json"),
                    ("kokoro_onnx_file", "models/kokoro/kokoro-v1.0.onnx"),
                    ("kokoro_voices", "models/kokoro/voices-v1.0.bin"),
                ):
                    p = os.path.join(state4, files)
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    with open(p, "w", encoding="utf-8") as f:
                        f.write("x")
                installed_json4 = os.path.join(state4, "installed.json")
                _atomic_write_json(installed_json4, {
                    "voice-piper": {"ok": True, "requires_venv": True,
                                     "files": ["models/piper/en_US-amy-medium.onnx",
                                               "models/piper/en_US-amy-medium.onnx.json",
                                               "models/piper/en_US-ryan-high.onnx",
                                               "models/piper/en_US-ryan-high.onnx.json"]},
                })
                det4 = detect()
                check("SELF-HEAL: an upgrade's missing audio-runtime record no longer "
                      "reads as 'not installed' when the runtime actually works",
                      det4["voice"]["piper"] is True and det4["voice_active"] == "piper")
                check("SELF-HEAL: repairs installed.json so the next call is fast",
                      _component_files_ok(_installed_record().get("audio-runtime")) is True)
                check("SELF-HEAL: repaired record is marked 'healed' for doctor/debugging",
                      _installed_record().get("audio-runtime", {}).get("healed") is True)

                # 3. kokoro's own record is ALSO missing (fully unrecorded, not just
                # audio-runtime) -- probing the package plus the actual model files
                # on disk must still recover it, and record it so it's fast next time.
                check("SELF-HEAL: kokoro fully unrecorded but importable + models on disk -> usable",
                      detect()["voice"]["kokoro"] is True)
                check("SELF-HEAL: kokoro gets its own repaired record",
                      _component_files_ok(_installed_record().get("voice-kokoro")) is True)

                # 4. qa: faster_whisper "importable" must NOT be enough on its own --
                # only the level whose model.bin is actually on disk should probe
                # present; the two share one package, so this is the check that
                # catches a probe that's too coarse.
                base_snapshot = os.path.join(
                    state4, "models", "whisper", "models--Systran--faster-whisper-base", "snapshots", "abc")
                os.makedirs(base_snapshot, exist_ok=True)
                with open(os.path.join(base_snapshot, "model.bin"), "w", encoding="utf-8") as f:
                    f.write("x")
                det_qa = detect()
                check("SELF-HEAL: qa-base probed present (its model.bin exists on disk)",
                      "base" in det_qa["qa"]["models"])
                check("SELF-HEAL: qa-medium NOT probed present (no model.bin for it, "
                      "even though the package imports fine) -- a coarse probe would "
                      "wrongly conflate the two",
                      "medium" not in det_qa["qa"]["models"])

                # 5. the opposite of a false negative: importable package, but the
                # actual downloaded voice files are gone -- must NOT probe present.
                os.remove(os.path.join(state4, "models", "piper", "en_US-amy-medium.onnx"))
                installed_json_data = json.load(open(installed_json4, encoding="utf-8"))
                del installed_json_data["voice-piper"]  # simulate an unrecorded, and now broken, install
                _atomic_write_json(installed_json4, installed_json_data)
                check("SELF-HEAL: package importable but its downloaded model files are "
                      "gone -> NOT probed present (a package-only probe would be fooled)",
                      detect()["voice"]["piper"] is False)
            finally:
                globals()["venv_python"] = real_venv_python
                globals()["subprocess"] = real_subprocess
                _PROBE_CACHE.clear()
                del os.environ["PODCAST_STATE_DIR"]

            # -- auto_setup: default, validation, and auto_setup_plan() --
            check("defaults: auto_setup", load()["auto_setup"] == "always")
            os.environ["PODCAST_AUTO_SETUP"] = "bogus"
            stderr_buf = io.StringIO()
            with contextlib.redirect_stderr(stderr_buf):
                cfg_bad_auto = load()
            check("invalid PODCAST_AUTO_SETUP rejected, falls back", cfg_bad_auto["auto_setup"] == "always")
            check("invalid PODCAST_AUTO_SETUP warns", "bogus" in stderr_buf.getvalue())
            del os.environ["PODCAST_AUTO_SETUP"]
            os.environ["PODCAST_AUTO_SETUP"] = "audio-only"
            check("PODCAST_AUTO_SETUP=audio-only accepted", load()["auto_setup"] == "audio-only")
            del os.environ["PODCAST_AUTO_SETUP"]

            # shape()'s own default has a present ffmpeg (most of the earlier tests
            # in this file want that baseline) -- these plan tests want a machine
            # with truly nothing at all, ffmpeg included.
            nothing_det = shape(ffmpeg=None, ffprobe=None)
            everything_det = shape(
                voice={"piper": True, "kokoro": True}, voice_active="kokoro",
                qa={"whisper_cli": None, "faster_whisper": True, "models": ["base"]}, qa_active="base")
            # The shape a 0.1.2 install is stuck in: piper renders, kokoro was never
            # fetched, voice_engine=auto resolves to piper forever.
            piper_only_det = shape(
                voice={"piper": True, "kokoro": False}, voice_active="piper",
                qa={"whisper_cli": None, "faster_whisper": True, "models": ["base"]}, qa_active="base")

            plan = auto_setup_plan(dict(base_cfg, auto_setup="always"), nothing_det)
            names = [c["component"] for c in plan["components"]]
            check("plan(always, nothing installed): ffmpeg first",
                  names and names[0] == "ffmpeg-static")
            check("plan(always, nothing installed): voice-kokoro next", "voice-kokoro" in names)
            check("plan(always, nothing installed): qa-base last", names and names[-1] == "qa-base")
            check("plan(always): total_bytes is the sum of its components",
                  plan["total_bytes"] == sum(c["bytes"] for c in plan["components"]))

            plan_audio = auto_setup_plan(dict(base_cfg, auto_setup="audio-only"), nothing_det)
            check("plan(audio-only): no qa component",
                  not any(c["kind"] == "qa" for c in plan_audio["components"]))
            check("plan(audio-only): still wants ffmpeg + voice",
                  {"ffmpeg", "voice"} == {c["kind"] for c in plan_audio["components"]})

            plan_never = auto_setup_plan(dict(base_cfg, auto_setup="never"), nothing_det)
            check("plan(never): installs nothing", plan_never["components"] == [])
            check("plan(never): user_said_never is True", plan_never["user_said_never"] is True)
            check("plan(audio-only): user_said_never is False", plan_audio["user_said_never"] is False)

            plan_only = auto_setup_plan(dict(base_cfg, auto_setup="always"), nothing_det, only="audio")
            check("plan(always, --only audio): narrows to audio-only for this call",
                  plan_only["effective_mode"] == "audio-only" and plan_only["mode"] == "always")
            plan_only_never = auto_setup_plan(dict(base_cfg, auto_setup="never"), nothing_det, only="audio")
            check("plan(never, --only audio): never still wins", plan_only_never["components"] == [])

            # -- HIGH4: an unrecognized `only` must be a loud error, never silent
            # no-op-that-widens-scope (found by review, 2026-09-12: `--only qa`,
            # `--only voice`, `--only Audio` all used to silently install
            # everything, ~1.1 GB, because only the literal "audio" was checked
            # and anything else fell through to no narrowing at all). --
            for bad_only in ("qa", "voice", "Audio", "ffmpeg"):
                try:
                    auto_setup_plan(base_cfg, nothing_det, only=bad_only)
                    check(f"HIGH4: auto_setup_plan(only={bad_only!r}) raises instead of silently widening scope",
                          False)
                except ValueError:
                    check(f"HIGH4: auto_setup_plan(only={bad_only!r}) raises ValueError", True)
            try:
                auto_setup_plan(base_cfg, nothing_det, only="")
                check("HIGH4: auto_setup_plan(only='') raises instead of silently widening scope", False)
            except ValueError:
                check("HIGH4: auto_setup_plan(only='') raises ValueError", True)
            check("HIGH4: auto_setup_plan(only=None) is still the normal, unnarrowed case",
                  auto_setup_plan(base_cfg, nothing_det, only=None)["effective_mode"] == "always")

            # -- MED: the announced download must not undersell the real disk
            # cost (found by review: ffmpeg's own archive is ~150 MB downloaded
            # but ~343 MB once unpacked -- 2.3x -- and a total that only ever
            # quoted one number was "the single thing most likely to make a user
            # distrust the next announcement"). --
            plan_bytes = auto_setup_plan(dict(base_cfg, auto_setup="always"), nothing_det)
            check("MED: plan() reports both total_bytes (disk) and total_download_bytes (wire)",
                  "total_download_bytes" in plan_bytes and "total_bytes" in plan_bytes)
            ffmpeg_entry = next(c for c in plan_bytes["components"] if c["component"] == "ffmpeg-static")
            check("MED: ffmpeg's disk estimate is measurably larger than its download estimate",
                  ffmpeg_entry["bytes"] > ffmpeg_entry["download_bytes"] > 0)
            check("MED: ffmpeg's numbers match the real measured sizes (150,109,916 / 342,771,408)",
                  ffmpeg_entry["download_bytes"] == 150_109_916 and ffmpeg_entry["bytes"] == 342_771_408)
            check("MED: total_download_bytes is the sum of each component's download_bytes",
                  plan_bytes["total_download_bytes"] == sum(c["download_bytes"] for c in plan_bytes["components"]))

            # -- HIGH4 acceptance test at the actual CLI boundary (not just the
            # function): `config.py plan --only qa` (or any non-"audio" value)
            # must exit 2 naming the valid values, not exit 0 with a full plan. --
            for bad_only in ("qa", "voice", "Audio"):
                r = subprocess.run([sys.executable, os.path.abspath(__file__), "plan", "--only", bad_only],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,
                                    env=dict(os.environ, PODCAST_CONFIG=cfg_path, PODCAST_STATE_DIR=state_path))
                check(f"HIGH4 CLI: 'plan --only {bad_only}' exits 2", r.returncode == 2)
                check(f"HIGH4 CLI: 'plan --only {bad_only}' names the valid values in its error",
                      "audio" in r.stderr.lower())
            r_ok = subprocess.run([sys.executable, os.path.abspath(__file__), "plan", "--only", "audio"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,
                                   env=dict(os.environ, PODCAST_CONFIG=cfg_path, PODCAST_STATE_DIR=state_path))
            check("HIGH4 CLI: 'plan --only audio' (the one valid value) exits 0", r_ok.returncode == 0)

            plan_off = auto_setup_plan(dict(base_cfg, auto_setup="always", voice_engine="none", qa_level="none"),
                                        nothing_det)
            check("plan(always): explicit voice_engine=none is still skipped",
                  not any(c["kind"] == "voice" for c in plan_off["components"]))
            check("plan(always): explicit qa_level=none is still skipped",
                  not any(c["kind"] == "qa" for c in plan_off["components"]))
            check("plan(always): ffmpeg is unaffected by voice/qa=none",
                  any(c["kind"] == "ffmpeg" for c in plan_off["components"]))

            plan_kokoro = auto_setup_plan(dict(base_cfg, auto_setup="always", voice_engine="kokoro"), nothing_det)
            voice_targets = [c["target"] for c in plan_kokoro["components"] if c["kind"] == "voice"]
            check("plan(always): explicit voice_engine=kokoro targets kokoro",
                  voice_targets == ["kokoro"])

            # -- The regression this file exists to prevent: a fresh machine under the
            # shipped default (voice_engine=auto, nothing installed) must auto-install
            # the BEST engine. It shipped targeting piper in 0.1.2; auto then resolved
            # to piper as "best installed" forever and the audio quality quietly
            # dropped, with nothing in the banner saying a better engine existed. --
            plan_auto = auto_setup_plan(dict(base_cfg, auto_setup="always", voice_engine="auto"), nothing_det)
            auto_voice = [c for c in plan_auto["components"] if c["kind"] == "voice"]
            check("plan(always): voice_engine=auto on a bare machine targets kokoro, not piper",
                  [c["target"] for c in auto_voice] == ["kokoro"])
            check("plan(always): the auto target's quoted size is kokoro's, not piper's",
                  [c["bytes"] for c in auto_voice] == [VOICE_DISK_BYTES["kokoro"]]
                  and [c["download_bytes"] for c in auto_voice] == [VOICE_DOWNLOAD_BYTES["kokoro"]])

            plan_piper = auto_setup_plan(dict(base_cfg, auto_setup="always", voice_engine="piper"), nothing_det)
            check("plan(always): explicit voice_engine=piper is still honoured (small/fast stays available)",
                  [c["target"] for c in plan_piper["components"] if c["kind"] == "voice"] == ["piper"])

            up_cfg = dict(base_cfg, auto_setup="always", voice_engine="auto")
            check("downgraded: piper active + no kokoro under auto is a downgrade",
                  voice_is_downgraded(up_cfg, piper_only_det) is True)
            check("downgraded: kokoro active is not a downgrade",
                  voice_is_downgraded(up_cfg, everything_det) is False)
            check("downgraded: an explicit voice_engine=piper is a choice, not a downgrade",
                  voice_is_downgraded(dict(up_cfg, voice_engine="piper"), piper_only_det) is False)
            check("downgraded: nothing installed at all is a gap, not a downgrade",
                  voice_is_downgraded(up_cfg, nothing_det) is False)

            plan_up = auto_setup_plan(up_cfg, piper_only_det)
            up_comps = [c for c in plan_up["components"] if c["kind"] == "voice"]
            check("migration: a piper-only machine plans the kokoro upgrade",
                  [c["component"] for c in up_comps] == ["voice-kokoro"])
            check("migration: it is labelled an upgrade, not a missing piece",
                  up_comps and up_comps[0].get("upgrade_from") == "piper")
            check("migration: piper is not re-planned alongside it",
                  "voice-piper" not in [c["component"] for c in plan_up["components"]])
            check("migration: the upgrade's bytes are counted in the total",
                  plan_up["total_bytes"] >= VOICE_DISK_BYTES["kokoro"])
            check("migration: auto_setup=never never upgrades behind the user's back",
                  auto_setup_plan(dict(up_cfg, auto_setup="never"), piper_only_det)["components"] == [])
            check("migration: an explicit voice_engine=piper is left alone",
                  not any(c["kind"] == "voice" for c in
                          auto_setup_plan(dict(up_cfg, voice_engine="piper"), piper_only_det)["components"]))

            st_up = status(up_cfg, piper_only_det)
            check("migration: status flags the downgrade", st_up["voice_downgraded"] is True)
            check("migration: the banner names kokoro in the voice row",
                  "kokoro" in st_up["voice"]["note"])
            check("migration: the upgrade is reported separately from real gaps",
                  st_up["auto_setup"]["upgrades"] == ["voice-kokoro"]
                  and "voice-kokoro" not in st_up["auto_setup"]["missing"])
            check("migration: a healthy machine flags nothing",
                  status(up_cfg, everything_det)["voice_downgraded"] is False)

            # status["config"]: the resolved settings the skill actually reads.
            st_cfg = status(dict(base_cfg, episodes_dir="/tmp/EP", default_cast="panel"),
                             everything_det)["config"]
            check("status exposes episodes_dir (SKILL.md has always read it from here)",
                  st_cfg["episodes_dir"] == "/tmp/EP")
            check("status exposes default_cast", st_cfg["default_cast"] == "panel")
            check("status exposes every setting, not a hand-picked few",
                  set(st_cfg) == set(DEFAULTS))

            plan_satisfied = auto_setup_plan(dict(base_cfg, auto_setup="always"), everything_det)
            check("plan(always, everything already installed): nothing to do",
                  plan_satisfied["components"] == [] and plan_satisfied["total_bytes"] == 0)

            # -- ffmpeg detection: bundled (our own state dir) wins over PATH --
            state6 = os.path.join(td, "state6")
            os.environ["PODCAST_STATE_DIR"] = state6
            try:
                bin_dir = os.path.join(state6, "bin")
                os.makedirs(bin_dir, exist_ok=True)
                fake_ffmpeg = os.path.join(bin_dir, "ffmpeg")
                fake_ffprobe = os.path.join(bin_dir, "ffprobe")
                for p in (fake_ffmpeg, fake_ffprobe):
                    with open(p, "w", encoding="utf-8") as f:
                        f.write("x")
                _atomic_write_json(os.path.join(state6, "installed.json"), {
                    "ffmpeg-static": {"ok": True, "requires_venv": False,
                                       "files": ["bin/ffmpeg", "bin/ffprobe"]},
                })
                ffmpeg_p, ffprobe_p, source = _ffmpeg_detect()
                check("ffmpeg detection: bundled copy found", source == "bundled")
                check("ffmpeg detection: bundled paths are absolute and under state dir",
                      ffmpeg_p == fake_ffmpeg and ffprobe_p == fake_ffprobe)

                det_bundled = detect()
                check("detect(): ffmpeg_source is 'bundled'", det_bundled["ffmpeg_source"] == "bundled")
                out_bundled = format_status(base_cfg, det_bundled)
                check("format_status(): shows 'bundled' for ffmpeg",
                      "ffmpeg" in out_bundled.lower() and "bundled" in out_bundled.lower())

                # remove the bundled record (e.g. requires_venv=False means it does
                # NOT depend on the venv -- deleting the venv must not affect it,
                # only deleting/uninstalling ffmpeg-static itself should)
                os.remove(os.path.join(state6, "installed.json"))
                ffmpeg_p2, ffprobe_p2, source2 = _ffmpeg_detect()
                sys_ffmpeg = shutil.which("ffmpeg")
                expected_source = "system" if sys_ffmpeg else None
                check("ffmpeg detection: falls back to system PATH once bundled record is gone",
                      source2 == expected_source and ffmpeg_p2 == sys_ffmpeg)
            finally:
                del os.environ["PODCAST_STATE_DIR"]

    finally:
        restore_env()

    return 0 if ok[0] else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_kv_args(items):
    updates = {}
    for item in items:
        if "=" not in item:
            print(f"error: expected key=value, got {item!r}", file=sys.stderr)
            sys.exit(1)
        key, _, val = item.partition("=")
        key = key.strip()
        if key not in DEFAULTS:
            print(f"error: unknown setting {key!r}. Known settings: {', '.join(sorted(DEFAULTS))}",
                  file=sys.stderr)
            sys.exit(1)
        choices = ENUM_CHOICES.get(key)
        if choices and val not in choices:
            print(f"error: {key} must be one of {', '.join(choices)}, got {val!r}", file=sys.stderr)
            sys.exit(1)
        updates[key] = val
    return updates


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)

    if argv and argv[0] == "--selftest":
        sys.exit(run_selftest())

    if not argv or argv[0] == "status":
        rest = argv[1:] if argv else []
        if "--json" in rest:
            print(json.dumps(status(), indent=2))
        else:
            print(format_status())
        return

    cmd, rest = argv[0], argv[1:]
    if cmd == "set":
        if not rest:
            print("error: usage: config.py set key=value [key=value ...]", file=sys.stderr)
            sys.exit(1)
        updates = _parse_kv_args(rest)
        new_cfg = save(updates)
        print(json.dumps(new_cfg, indent=2, sort_keys=True))
    elif cmd == "path":
        print(config_path())
    elif cmd == "plan":
        only = None
        for i, a in enumerate(rest):
            if a == "--only" and i + 1 < len(rest):
                only = rest[i + 1]
        # HIGH4: an unrecognized --only value must be a loud, named error, not a
        # silent "well then I guess no narrowing" that installs everything.
        if only is not None and only not in AUTO_SETUP_ONLY_VALUES:
            print(f"error: --only expects one of {', '.join(AUTO_SETUP_ONLY_VALUES)}, got {only!r}",
                  file=sys.stderr)
            sys.exit(2)
        print(json.dumps(auto_setup_plan(only=only), indent=2))
    else:
        print(f"error: unknown command {cmd!r}", file=sys.stderr)
        print("usage: config.py [status [--json] | set key=value ... | path | plan [--only audio] | --selftest]",
              file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
