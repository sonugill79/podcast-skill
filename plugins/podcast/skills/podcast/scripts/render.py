#!/usr/bin/env python3
"""
render.py: turn a two-host podcast script into one MP3 with a local TTS engine.

Script format (plain text):
  MAYA: A line of dialogue.          speaker lines; SPEAKER must be in --voices
  ALEX: Another line.
  [pause 1.5]                        explicit silence, seconds
  ---                                segment break (longer pause)
  # ── 1. Title ──                   chapter header (box-drawing dashes around a title;
                                      a divider with no title text is just a comment)
  # anything else                    comment, ignored
  blank lines                        ignored

Three voice engines are supported (see ENGINE_DEFAULTS below for the per-engine
default voice table):
  kokoro        kokoro-onnx -- ONNX model + voice pack, no torch/GPU required
  kokoro-torch  the original torch-based `kokoro` package, kept working if installed
  piper         piper-tts -- smaller/faster, ~22.05 kHz

Engine choice: --engine > config.load()['voice_engine'] > best installed per
config.detect(). If none is installed, exits 3 with a friendly upgrade hint.

Rendered lines are cached by (engine, voice, sample rate, speed, spoken-text,
model+trim version) under <script-dir>/.tts-cache/ (override with --cache DIR), so
two renders of the same script -- draft and final, two output names, or two
engines -- never collide or serve one engine's audio under another's key. Cache
writes are atomic (write-then-rename), and a cache file that turns out unreadable,
empty, or at the wrong sample rate is deleted and re-rendered rather than trusted.
A --lexicon FILE rewrites words before TTS only (the script keeps the true
spelling). Default: <directory of SCRIPT>/lexicon.txt if the episode has its own
copy, else the skill's own templates/lexicon.txt; see default_lexicon_path() below.
Neither existing is a silent no-op, same as today.

  /path/to/tts-venv/bin/python render.py script.txt episode.mp3 \\
      --engine kokoro-torch --voices MAYA=af_heart,ALEX=am_michael [--speed 1.0] \\
      [--cache DIR] [--lexicon FILE]

  --dry-run    parse + lexicon only, print line/word/duration estimate and chapters (no
               audio, no OUT required, no engine resolved)
  --selftest   offline parser/lexicon/estimate/engine-selection checks, prints
               PASS/FAIL per check, exits 0/1
"""
import argparse, difflib, glob, hashlib, json, os, re, sys, time

try:
    import config
except ImportError:
    config = None

ORPHAN_TMP_RE = re.compile(r'^(?P<name>.+)\.tmp-(?P<pid>\d+)$')
ORPHAN_TMP_MAX_AGE = 3600  # seconds

TURN_GAP, SEGMENT_GAP = 0.32, 1.1
# Speech-only words/minute, derived from a measured production episode: 3,131
# spoken words over a measured 1230.0 s render, minus the 41.7 s of turn/segment/
# pause gaps this parser computes for that script -> 3131 words / 1188.3 s of
# actual speech = ~158.1 wpm. (The old constant, 153, had already baked the gaps in
# once, then the dry-run estimate added them again -- 21.2 min vs a measured 20.5.)
# Re-derive this constant if TURN_GAP/SEGMENT_GAP change materially.
WPM = 158

KOKORO_REPO_ID = 'hexgrad/Kokoro-82M'
TRIM_THRESHOLD_DB = -45
TRIM_PAD = (0.03, 0.08)  # seconds kept before/after the detected sound, when trimming
# Bump this if the trim parameters above change, to invalidate old cache entries
# rendered under different settings. Per-engine model/version identity is folded
# in separately by cache_key() below, since it differs by engine.
CACHE_VERSION = f'trim{TRIM_THRESHOLD_DB}dB-{TRIM_PAD[0]}-{TRIM_PAD[1]}'

# Bumped whenever a given engine's model/weights identity changes, so switching
# (or upgrading) an engine invalidates only that engine's old cache entries.
ENGINE_CACHE_VERSION = {
    'kokoro-torch': KOKORO_REPO_ID,
    'kokoro': 'kokoro-onnx-v1',
    'piper': 'piper-v1',
}

# Per-engine defaults: native sample rate and a two-speaker (female, male) voice
# table, so --voices is optional. The speaker names themselves (MAYA/ALEX) are
# fixed across engines -- only the underlying per-engine voice id differs.
ENGINE_DEFAULTS = {
    'kokoro':       {'sample_rate': 24000, 'voices': {'MAYA': 'af_heart', 'ALEX': 'am_michael'}},
    'kokoro-torch': {'sample_rate': 24000, 'voices': {'MAYA': 'af_heart', 'ALEX': 'am_michael'}},
    # Matches the voice pack setup.sh actually downloads (rhasspy/piper-voices v1.0.0).
    'piper':        {'sample_rate': 22050, 'voices': {'MAYA': 'en_US-amy-medium', 'ALEX': 'en_US-ryan-high'}},
}

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(REPO_ROOT, 'templates')
CASTS_DIR = os.path.join(REPO_ROOT, 'casts')

# The voices in the kokoro v1.0 pack setup.sh downloads (checksum-pinned, so this
# list is stable). Used to reject a mistyped voice id up front: without it, a typo
# surfaces as an exception inside kokoro_onnx after the model has loaded and the
# episode's research has already been paid for. Prefix is language+gender --
# a=American, b=British, e=Spanish, f=French, h=Hindi, i=Italian, j=Japanese,
# p=Portuguese, z=Mandarin; f=female, m=male.
KOKORO_VOICE_IDS = frozenset("""
af_alloy af_aoede af_bella af_heart af_jessica af_kore af_nicole af_nova af_river
af_sarah af_sky am_adam am_echo am_eric am_fenrir am_liam am_michael am_onyx
am_puck am_santa bf_alice bf_emma bf_isabella bf_lily bm_daniel bm_fable bm_george
bm_lewis ef_dora em_alex em_santa ff_siwis hf_alpha hf_beta hm_omega hm_psi if_sara
im_nicola jf_alpha jf_gongitsune jf_nezumi jf_tebukuro jm_kumo pf_dora pm_alex
pm_santa zf_xiaobei zf_xiaoni zf_xiaoxiao zf_xiaoyi zm_yunjian zm_yunxi zm_yunxia
zm_yunyang
""".split())


def validate_kokoro_voices(voices, source):
    """Reject a voice id kokoro doesn't have, naming the closest real one.

    Only for the kokoro engines -- piper's voice names are model filenames and are
    already checked by _make_piper_engine() before any audio is synthesized."""
    for speaker, voice in sorted(voices.items()):
        if voice in KOKORO_VOICE_IDS:
            continue
        near = difflib.get_close_matches(voice, sorted(KOKORO_VOICE_IDS), n=3, cutoff=0.6)
        hint = f' -- did you mean {", ".join(near)}?' if near else ''
        die(f'{source}: {speaker}={voice!r} is not a kokoro voice{hint}\n'
            f'  (54 available; see casts/README.md)', 2)

CHAPTER_RE = re.compile(r'^#\s*─+\s*(.+?)\s*─*\s*$')


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def default_lexicon_path(script_path):
    """<directory of the script being rendered>/lexicon.txt, falling back to the
    skill's own templates/lexicon.txt when the episode directory doesn't have its
    own copy -- episodes keep their own lexicon, but a fresh episode dir (or one
    that predates this convention) has neither, in which case the skill's
    generic template still applies before TTS. Neither existing is unchanged from
    today: load_lexicon() silently no-ops on a missing implicit-default path."""
    episode_path = os.path.join(os.path.dirname(os.path.abspath(script_path)) or '.', 'lexicon.txt')
    if os.path.exists(episode_path):
        return episode_path
    template_path = os.path.join(TEMPLATES_DIR, 'lexicon.txt')
    if os.path.exists(template_path):
        return template_path
    return episode_path  # doesn't exist either; load_lexicon()'s no-op handles it


def load_lexicon(path, explicit=False):
    """Parse 'written => spoken' rules, one per line; blank/# lines ignored.
    Returns a compiled regex (longest written-form first, word boundaries) and a
    dict written->spoken, or (None, {}) if the file is missing -- a silent no-op
    only for the implicit default path; a path the caller explicitly asked for
    (--lexicon) is an error if it doesn't exist. Warns (stderr) on a malformed line
    (no '=>') and on a duplicate 'written' key (last one wins)."""
    if not path or not os.path.exists(path):
        if explicit:
            die(f'{path}: --lexicon file not found', 2)
        return None, {}
    rules = {}
    for n, raw in enumerate(open(path, encoding='utf-8'), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '=>' not in line:
            print(f'{path}:{n}: warning: malformed lexicon line (no "=>"), skipped: {line[:60]}',
                  file=sys.stderr)
            continue
        written, spoken = line.split('=>', 1)
        written, spoken = written.strip(), spoken.strip()
        if not written:
            continue
        if written in rules and rules[written] != spoken:
            print(f'{path}:{n}: warning: duplicate lexicon rule for {written!r}: '
                  f'{spoken!r} wins over {rules[written]!r}', file=sys.stderr)
        rules[written] = spoken
    if not rules:
        return None, rules
    # Longest written form first, so e.g. "X-team" beats a shorter overlapping rule.
    ordered = sorted(rules, key=len, reverse=True)
    alt = '|'.join(re.escape(w) for w in ordered)
    # Plain \w boundaries (not [\w-]): a hyphen is not a word char, so "ex-Globex" or
    # "Globex-style" still exposes "Globex" to a rule at that edge, while
    # "X-teams" and "BX-team" stay protected by the letter on the wrong side of the
    # boundary either way.
    pattern = re.compile(r'(?<!\w)(' + alt + r')(?!\w)')
    return pattern, rules


def apply_lexicon(text, pattern, rules):
    if not pattern:
        return text
    return pattern.sub(lambda m: rules[m.group(1)], text)


def parse_voices(spec):
    voices = {}
    for kv in spec.split(','):
        if '=' not in kv:
            die(f'--voices: malformed entry (expected SPEAKER=voice): {kv!r}', 2)
        k, v = kv.split('=', 1)
        k, v = k.strip(), v.strip()
        if not k or not v:
            die(f'--voices: malformed entry (expected SPEAKER=voice): {kv!r}', 2)
        voices[k] = v
    return voices


CAST_FENCE = 'cast'


def parse_cast(text, source='<cast>'):
    """Parse a cast file's ```cast block into ({SPEAKER: voice}, {SPEAKER: speed},
    {SPEAKER: [voice, ...]}) -- the third is the rotation pool for each slot.

    The block is the one machine-readable part of an otherwise prose file -- the
    rest of a cast describes how each host talks, which only the script writer
    reads. One line per speaker:

        MODERATOR = bf_emma @ 0.98
        SKEPTIC   = af_nicole            # speed defaults to 1.0

    Everything else in the file is ignored, so a cast stays a document a person
    can read. Parsed here rather than transcribed into --voices by the caller so
    a typo is a real error with a line number instead of a wrong voice nobody
    notices until the episode is rendered."""
    lines = text.splitlines()
    start = end = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start is None:
            if stripped.startswith('```') and stripped[3:].strip() == CAST_FENCE:
                start = i + 1
        elif stripped.startswith('```'):
            end = i
            break
    if start is None:
        die(f'{source}: no ```{CAST_FENCE} block -- a cast file must declare its '
            f'voices (SPEAKER = voice [@ speed], one per line)', 2)
    if end is None:
        die(f'{source}:{start}: ```{CAST_FENCE} block is never closed', 2)

    voices, speeds, pools = {}, {}, {}
    for offset, raw in enumerate(lines[start:end]):
        n = start + offset + 1  # 1-based, for the error message
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if '=' not in line:
            die(f'{source}:{n}: expected SPEAKER = voice [@ speed], got: {raw.strip()[:60]!r}', 2)
        speaker, rest = line.split('=', 1)
        speaker = speaker.strip()
        voice_text, _, speed_text = (x.strip() for x in rest.partition('@'))
        # A slot may offer several interchangeable voices; one is chosen per episode
        # (see choose_voices). The first is the slot's default and its --no-rotate
        # pick, so put the safest choice first.
        pool = [v.strip() for v in voice_text.split(',') if v.strip()]
        if not speaker or not pool:
            die(f'{source}:{n}: expected SPEAKER = voice[, voice...] [@ speed], '
                f'got: {raw.strip()[:60]!r}', 2)
        if len(set(pool)) != len(pool):
            die(f'{source}:{n}: {speaker} lists the same voice twice', 2)
        voice = pool[0]
        if speaker in voices:
            die(f'{source}:{n}: {speaker} is listed twice in the cast', 2)
        speed = 1.0
        if speed_text:
            try:
                speed = float(speed_text)
            except ValueError:
                die(f'{source}:{n}: {speed_text!r} is not a number (speed, e.g. @ 1.05)', 2)
            # A cast is meant to vary pace by a few percent for character. Anything
            # outside this is a typo (@ 10 for @ 1.0), and kokoro turns it into
            # unlistenable audio rather than failing, so catch it here.
            if not 0.5 <= speed <= 2.0:
                die(f'{source}:{n}: speed {speed} is outside 0.5-2.0', 2)
        voices[speaker] = voice
        speeds[speaker] = speed
        pools[speaker] = pool
    if not voices:
        die(f'{source}: the ```{CAST_FENCE} block is empty -- no speakers declared', 2)
    return voices, speeds, pools


def parse_voices_list(spec):
    """"af_nova, am_santa" -> ['af_nova', 'am_santa']; anything falsy -> []."""
    if not spec:
        return []
    return [v.strip() for v in str(spec).split(',') if v.strip()]


def parse_speeds(spec):
    """--speeds SPEAKER=1.05[,SPEAKER=0.98...] -> {SPEAKER: float}."""
    speeds = {}
    for kv in spec.split(','):
        if '=' not in kv:
            die(f'--speeds: malformed entry (expected SPEAKER=number): {kv!r}', 2)
        k, v = (x.strip() for x in kv.split('=', 1))
        if not k or not v:
            die(f'--speeds: malformed entry (expected SPEAKER=number): {kv!r}', 2)
        try:
            speeds[k] = float(v)
        except ValueError:
            die(f'--speeds: {v!r} is not a number (e.g. {k}=1.05)', 2)
        if not 0.5 <= speeds[k] <= 2.0:
            die(f'--speeds: {k}={speeds[k]} is outside 0.5-2.0', 2)
    return speeds


# Sentinel for "argument not supplied", so a caller can pass None meaningfully.
_UNSET = object()

ROTATION_FILE = 'voice-rotation.json'
LOCK_NAME = 'cast.lock.json'


def _read_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            v = json.load(f)
        return v if isinstance(v, type(default)) else default
    except (OSError, ValueError):
        return default


def rotation_path(which_config=_UNSET):
    cfg = config if which_config is _UNSET else which_config
    if not cfg:
        return None
    try:
        return os.path.join(cfg.state_dir(), ROTATION_FILE)
    except Exception:
        return None


def choose_voices(pools, recent=None, blocked=(), rotate=True):
    """Pick one voice per slot: the least recently used one that isn't blocked.

    `recent` maps slot -> list of voice ids, most recent last (what the previous
    episodes used). Rotation keeps a series from sounding identical every week
    without ever being random -- random would re-pick on every re-render and blow
    the per-line TTS cache, which is keyed on the voice.

    Blocked voices are dropped first: "I don't like that voice" should hold across
    every cast, so it is a user setting rather than a cast edit."""
    blocked = {b.strip() for b in blocked if b and b.strip()}
    recent = recent or {}
    chosen = {}
    for slot, pool in pools.items():
        allowed = [v for v in pool if v not in blocked]
        if not allowed:
            die(f'{slot}: every voice in this cast slot ({", ".join(pool)}) is on the '
                f'blocklist -- clear one with: config.py set voice_blocklist=<ids>', 2)
        if not rotate:
            chosen[slot] = allowed[0]
            continue
        history = [v for v in recent.get(slot, []) if v in allowed]
        # Least recently used, ties broken by the cast's own order.
        chosen[slot] = min(allowed, key=lambda v: (history.index(v) if v in history else -1,
                                                    allowed.index(v)))
    return chosen


def record_rotation(recent, chosen, keep=8):
    """Fold this episode's picks into the history, most recent last."""
    out = {k: list(v) for k, v in (recent or {}).items()}
    for slot, voice in chosen.items():
        hist = [v for v in out.get(slot, []) if v != voice]
        hist.append(voice)
        out[slot] = hist[-keep:]
    return out


def resolve_cast(args, engine_id):
    """(voices, speeds) from --cast / --voices / --speeds / the engine default table.

    Precedence, lowest to highest: the engine's default two-speaker table, then a
    --cast file, then explicit --voices / --speeds entries (per speaker, so one
    voice can be swapped without restating the cast). --speed stays the baseline
    for any speaker a cast doesn't pace."""
    voices, speeds, pools = {}, {}, {}
    if args.cast:
        try:
            with open(args.cast, encoding='utf-8') as f:
                text = f.read()
        except OSError as e:
            die(f'--cast {args.cast}: {e.strerror or e}', 2)
        voices, speeds, pools = parse_cast(text, args.cast)
    elif not args.voices:
        voices = default_voices_for(engine_id or 'kokoro')
    if args.voices:
        explicit = parse_voices(args.voices)
        voices.update(explicit)
        # An explicitly named voice is a decision, not a suggestion -- it leaves the
        # rotation entirely rather than becoming a one-entry pool alongside it.
        for sp in explicit:
            pools.pop(sp, None)
    if args.speeds:
        speeds.update(parse_speeds(args.speeds))
    speeds = {sp: speeds.get(sp, args.speed) for sp in voices}
    if (engine_id or '').startswith('kokoro'):
        validate_kokoro_voices(voices, args.cast or '--voices')
    return voices, speeds, pools


def apply_rotation(voices, pools, args, cache_dir):
    """Resolve each rotating slot to one voice, and remember the choice.

    A lock file in the episode's own cache dir pins the picks, so re-rendering an
    episode after fixing three lines gets the same voices (and the same warm cache)
    rather than a new draw."""
    rotating = {sp: pool for sp, pool in pools.items() if len(pool) > 1}
    if not rotating:
        return voices, None
    lock_path = os.path.join(cache_dir, LOCK_NAME)
    locked = _read_json(lock_path, {})
    pinned = {sp: v for sp, v in locked.items() if sp in rotating and v in rotating[sp]}
    todo = {sp: pool for sp, pool in rotating.items() if sp not in pinned}

    blocked = list(args.exclude_voices)
    rot_path = rotation_path()
    recent = _read_json(rot_path, {}) if rot_path else {}
    fresh = choose_voices(todo, recent, blocked, rotate=not args.no_rotate) if todo else {}

    chosen = dict(pinned, **fresh)
    out = dict(voices, **chosen)
    if fresh and rot_path:
        try:
            atomic_write(rot_path, lambda tmp: _write_json(tmp, record_rotation(recent, fresh)))
        except OSError:
            pass  # an unwritable state dir must never fail a render
    try:
        os.makedirs(cache_dir, exist_ok=True)
        atomic_write(lock_path, lambda tmp: _write_json(tmp, chosen))
    except OSError:
        pass
    return out, {'chosen': chosen, 'pinned': sorted(pinned), 'pools': rotating}


def _write_json(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2)


def default_voices_for(engine_id):
    """The (female, male) default voice table for one engine, or kokoro's if the
    engine id isn't recognized -- used only when --voices is omitted."""
    return dict(ENGINE_DEFAULTS.get(engine_id, ENGINE_DEFAULTS['kokoro'])['voices'])




def select_engine(cli_engine, which_config=_UNSET):
    """--engine flag > config.load()['voice_engine'] > best installed per
    config.detect()['voice_active']. Exits 3 (not a crash) if nothing is available
    -- the /podcast skill turns that into a friendly upgrade prompt. `which_config`
    lets callers (selftest) inject a fake config module -- or explicitly `None` to
    simulate no config module at all -- without touching the real one; production
    code never passes it, which means "use the real module-level `config`, if
    importable" (distinct from an explicit `None`, which means "there is none").

    config.py's own DEFAULTS ship voice_engine="auto" (its sentinel for "no explicit
    choice, use whatever's installed") and "none" (explicitly no engine); neither is
    a real engine id, so both fall through to detect() here exactly like an unset
    value would -- only an actual engine name (including "kokoro-torch", which
    config.py's own installer doesn't manage but this script still honors) is
    returned directly."""
    if cli_engine:
        return cli_engine
    cfg = config if which_config is _UNSET else which_config
    if cfg:
        try:
            engine = cfg.load().get('voice_engine')
        except Exception:
            engine = None
        if engine and engine not in ('auto', 'none'):
            if engine not in ENGINE_DEFAULTS:
                # A garbage/mistyped/wrong-case value (e.g. PODCAST_VOICE_ENGINE=Kokoro)
                # would otherwise silently fall through to "no voice engine installed",
                # which is a misleading message when something IS configured -- just
                # not a name this script recognizes.
                die(f"unknown engine {engine!r} (known: {', '.join(sorted(ENGINE_DEFAULTS))})", 2)
            return engine
        try:
            active = cfg.detect().get('voice_active')
        except Exception:
            active = None
        if active:
            return active
    die('no voice engine installed — run: /podcast upgrade voice', 3)


def resolve_ffmpeg(which_config=_UNSET):
    """Absolute path to ffmpeg from config.detect()['ffmpeg'] (a bundled,
    sudo-free copy in the state dir is preferred there over PATH), falling back
    to the bare 'ffmpeg' name -- resolved via PATH at exec time, same as always
    -- when config isn't importable, so a bare checkout with no config.py still
    works exactly as it did before this existed. Does not itself verify the
    result exists; a missing ffmpeg surfaces at the point of use (see the
    FileNotFoundError handling around the actual subprocess.run call)."""
    cfg = config if which_config is _UNSET else which_config
    if cfg:
        try:
            path = cfg.detect().get('ffmpeg')
        except Exception:
            path = None
        if path:
            return path
    return 'ffmpeg'


def cache_key(engine_id, voice, sample_rate, speed, spoken_text):
    """The cache key folds in the engine id, its model/weights version, the voice
    name, and the sample rate -- so switching engines (or a voice/engine pairing
    that happens to share a cache dir) never serves audio rendered by a different
    engine."""
    engine_version = ENGINE_CACHE_VERSION.get(engine_id, engine_id)
    return hashlib.sha1(
        f'{engine_id}|{engine_version}|{voice}|{sample_rate}|{speed}|{spoken_text}|{CACHE_VERSION}'
        .encode()).hexdigest()[:16]


def parse_script(path, voices, pattern, rules):
    """Returns (events, chapters) where events is a list of
    ('say', speaker, written_text, spoken_text) | ('pause', seconds)
    and chapters is a list of (title, event_index) — event_index is the index in
    `events` of the next say/pause after the header, i.e. where the chapter starts."""
    events = []
    chapters = []
    for n, raw in enumerate(open(path, encoding='utf-8'), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith('#'):
            m = CHAPTER_RE.match(line)
            if m:
                title = m.group(1)
                if re.search(r'[^─\s]', title):  # a divider alone ("# ────") isn't a chapter
                    chapters.append((title, len(events)))
            continue
        if line == '---':
            events.append(('pause', SEGMENT_GAP))
            continue
        if m := re.fullmatch(r'\[pause ([\d.]+)\]', line):
            try:
                secs = float(m.group(1))
            except ValueError:
                sys.exit(f'{path}:{n}: invalid pause duration: {line[:60]}')
            events.append(('pause', secs))
            continue
        m = re.fullmatch(r'([A-Z]+):\s*(.+)', line)
        if not m or m.group(1) not in voices:
            sys.exit(f'{path}:{n}: not a known speaker line: {line[:60]}')
        written = m.group(2)
        spoken = apply_lexicon(written, pattern, rules)
        events.append(('say', m.group(1), written, spoken))
    return events, chapters


def estimate_seconds(events):
    """Returns (total_seconds, chapter_start_seconds_by_event_index)."""
    t = 0.0
    starts = {}
    for i, ev in enumerate(events):
        starts[i] = t
        if ev[0] == 'pause':
            t += ev[1]
            continue
        words = len(ev[3].split())
        t += words / WPM * 60.0
        nxt = events[i + 1] if i + 1 < len(events) else None
        if nxt and nxt[0] == 'say':
            t += TURN_GAP
    starts[len(events)] = t
    return t, starts


def atomic_write(path, write_fn):
    """write_fn(tmp_path) must fully create tmp_path or raise; the tmp file then
    replaces `path` atomically (os.replace, same filesystem). A killed process or a
    concurrent writer to the same `path` therefore never leaves, or sees, a partial
    file at `path` itself -- only ever the old complete file or the new complete
    one. Any tmp leftover (a raised write_fn, a crash between write and replace) is
    cleaned up."""
    tmp = f'{path}.tmp-{os.getpid()}'
    try:
        write_fn(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def pid_alive(pid):
    """Best-effort liveness check via signal 0 (sends nothing, just probes)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just owned by someone else
    except OSError:
        return False
    return True


def cleanup_orphan_tmp_files(cache_dir, now=None, is_alive=pid_alive):
    """Delete a '<name>.tmp-<pid>' file only if it's older than ORPHAN_TMP_MAX_AGE
    or its embedded pid is no longer running -- never a blanket sweep, which would
    delete a concurrent renderer's in-progress file out from under it. A file that
    is both recent AND owned by a live pid is left alone."""
    now = time.time() if now is None else now
    try:
        entries = os.listdir(cache_dir)
    except OSError:
        return
    for name in entries:
        m = ORPHAN_TMP_RE.match(name)
        if not m:
            continue
        path = os.path.join(cache_dir, name)
        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue
        if age > ORPHAN_TMP_MAX_AGE or not is_alive(int(m.group('pid'))):
            try:
                os.remove(path)
            except OSError:
                pass


def title_from_out(out_path):
    """"tidal-energy-explained.mp3" -> "Tidal Energy Explained" -- a real title in a
    podcast app is better than the filename, and better than nothing."""
    stem = os.path.splitext(os.path.basename(out_path))[0]
    words = [w for w in re.split(r'[-_\s]+', stem) if w]
    return ' '.join(w if w.isupper() else w.capitalize() for w in words) or stem


def _ffmetadata_escape(value):
    """ffmetadata is line-based: =, ;, #, \\ and newlines must be escaped or the
    file silently reparses into the wrong fields."""
    out = []
    for ch in str(value):
        if ch in '=;#\\':
            out.append('\\' + ch)
        elif ch == '\n':
            out.append('\\\n')
        else:
            out.append(ch)
    return ''.join(out)


def build_ffmetadata(tags, chapter_records, duration):
    """An ffmpeg FFMETADATA1 document: global tags plus one [CHAPTER] per record.

    Chapter ends are the next chapter's start (the last one runs to `duration`),
    in milliseconds -- players show a chapter list built from these, which is what
    turns a long file into something you can skip around in."""
    lines = [';FFMETADATA1']
    for k, v in tags.items():
        if v:
            lines.append(f'{k}={_ffmetadata_escape(v)}')
    for i, ch in enumerate(chapter_records):
        start = max(0.0, float(ch['start']))
        end = float(chapter_records[i + 1]['start']) if i + 1 < len(chapter_records) else float(duration)
        # A zero- or negative-length chapter makes ffmpeg drop the whole chapter
        # list; keep every entry at least a millisecond long and ordered.
        end = max(end, start + 0.001)
        lines += ['[CHAPTER]', 'TIMEBASE=1/1000',
                  f'START={int(round(start * 1000))}', f'END={int(round(end * 1000))}',
                  f'title={_ffmetadata_escape(ch["title"])}']
    return '\n'.join(lines) + '\n'


def encode_mp3(wav_path, out_path, tags, chapter_records=(), duration=None,
                cover=None, ffmpeg_path=None):
    """Encode WAV -> tagged, chaptered MP3 and clean up the sidecar metadata file.

    One place, so every mp3 this skill produces is loudness-normalised the same way
    and carries the same tag set -- an episode and a voice audition included."""
    import subprocess  # local, matching this file's style for non-hot-path imports
    ffmpeg_path = resolve_ffmpeg() if ffmpeg_path is None else ffmpeg_path
    if duration is None and chapter_records:
        duration = max(float(c['start']) for c in chapter_records) + 1.0
    meta_path = os.path.splitext(out_path)[0] + '.ffmetadata'
    with open(meta_path, 'w', encoding='utf-8') as f:
        f.write(build_ffmetadata(tags, list(chapter_records), duration or 0.0))
    cmd = [ffmpeg_path, '-y', '-loglevel', 'error', '-i', wav_path, '-i', meta_path]
    if cover:
        if not os.path.exists(cover):
            die(f'--cover {cover}: no such file', 2)
        cmd += ['-i', cover]
    cmd += ['-map_metadata', '1', '-map', '0:a']
    if cover:
        # An attached picture is a video stream to ffmpeg; copy it through and mark
        # it as front cover art so players show it instead of trying to play it.
        cmd += ['-map', '2:v', '-c:v', 'copy', '-disposition:v:0', 'attached_pic']
    cmd += ['-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-ac', '1', '-b:a', '96k',
            '-id3v2_version', '3', '-write_id3v1', '1', out_path]
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        # Distinct from "no voice engine installed" and "audio runtime incomplete"
        # -- the engine and its Python runtime can both be fine while ffmpeg (a
        # separate native binary, previously assumed to be on PATH) is what's
        # missing. Named specifically so the fix is obvious rather than sending
        # someone back down the voice-engine troubleshooting path.
        die('ffmpeg not found — run: /podcast upgrade audio', 3)
    finally:
        if os.path.exists(meta_path):
            os.remove(meta_path)


def fmt_mmss(seconds):
    seconds = max(0.0, seconds)
    return f'{int(seconds // 60)}:{int(seconds % 60):02d}'


def build_arg_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument('script', nargs='?')
    ap.add_argument('out', nargs='?')
    ap.add_argument('--engine', choices=sorted(ENGINE_DEFAULTS), default=None,
                     help="voice engine: kokoro (onnx, default), kokoro-torch, piper. "
                          "Falls back to config.load()['voice_engine'], then whatever "
                          "config.detect() finds installed.")
    ap.add_argument('--voices', default=None,
                     help="SPEAKER=voice[,SPEAKER=voice...]; if omitted, uses the "
                          "selected engine's own default two-speaker table "
                          "(MAYA=female, ALEX=male)")
    ap.add_argument('--cast', default=None,
                     help='cast file (see casts/); its ```cast block binds each '
                          'SPEAKER to a voice and an optional pace')
    ap.add_argument('--no-rotate', action='store_true',
                     help="always take a cast slot's first voice instead of rotating "
                          'between its alternatives')
    ap.add_argument('--exclude-voices', default='', type=lambda v: [x.strip() for x in v.split(',') if x.strip()],
                     help='voice ids to drop from every rotation pool, comma-separated '
                          "(a user's \"not that one\" list; config voice_blocklist is "
                          'merged in automatically)')
    ap.add_argument('--speeds', default=None,
                     help='SPEAKER=1.05[,SPEAKER=0.98...] -- per-speaker pace, '
                          'overriding a --cast entry or --speed for those speakers')
    ap.add_argument('--speed', type=float, default=1.0,
                     help='baseline pace for every speaker a cast or --speeds '
                          'does not set (default 1.0)')
    # Episode metadata. Without these an episode arrives in a podcast app as an
    # untitled blob; chapters are always embedded (see write_ffmetadata).
    ap.add_argument('--title', default=None,
                     help='episode title (default: derived from the output filename)')
    ap.add_argument('--album', default=None, help='show name (default: "Podcast")')
    ap.add_argument('--artist', default=None,
                     help='hosts (default: the cast\'s speakers, in script order)')
    ap.add_argument('--date', default=None, help='YYYY-MM-DD (default: today)')
    ap.add_argument('--cover', default=None,
                     help='cover image (jpg/png) to embed as episode artwork')
    ap.add_argument('--cache', default=None)
    ap.add_argument('--lexicon', default=None,
                     help='pronunciation rules file; default is <directory of SCRIPT>/'
                          'lexicon.txt if the episode has one, else the templates/lexicon.txt '
                          'shipped with this skill (see default_lexicon_path())')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    return ap


# ------------------------------------------------------------------- engines

class _Engine:
    """name: engine id; sample_rate: native output rate in Hz; synth(text, voice,
    speed) -> np.float32 mono array at that rate."""

    def __init__(self, name, sample_rate, synth_fn):
        self.name = name
        self.sample_rate = sample_rate
        self.synth = synth_fn


def _models_base():
    return config.models_dir() if config else os.path.join(
        os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share')), 'topic-podcast', 'models')


# Anything smaller than this cannot be a real model/voice-pack file -- a 0-byte or
# truncated download (interrupted transfer, a proxy's HTML error page saved under
# the expected name) must read as "not installed", not crash 30 lines deep inside
# onnxruntime with a raw RuntimeError/JSONDecodeError.
MIN_MODEL_BYTES = 1024
MIN_VOICE_CONFIG_BYTES = 2  # a real .onnx.json is at least "{}"'s worth


def _check_model_file(path, min_bytes=MIN_MODEL_BYTES):
    """Raises FileNotFoundError (caught uniformly by make_engine) if `path` is
    missing, unreadable, or too small to be a real model file."""
    try:
        size = os.path.getsize(path)
    except OSError:
        raise FileNotFoundError(path)
    if size < min_bytes:
        raise FileNotFoundError(f'{path} (only {size} bytes -- looks corrupt/truncated)')


def _kokoro_model_paths():
    # setup.sh's voice-kokoro component downloads into <models_dir>/kokoro/.
    base = os.path.join(_models_base(), 'kokoro')
    model = os.path.join(base, 'kokoro-v1.0.onnx')
    voices = os.path.join(base, 'voices-v1.0.bin')
    _check_model_file(model)
    _check_model_file(voices)
    return model, voices


def _piper_model_path(voice_name):
    # setup.sh's voice-piper component downloads into <models_dir>/piper/, one
    # <voice>.onnx + <voice>.onnx.json pair per voice (PiperVoice.load's own
    # default is exactly "<model_path>.json", so that's what's checked here too).
    model = os.path.join(_models_base(), 'piper', f'{voice_name}.onnx')
    _check_model_file(model)
    _check_model_file(f'{model}.json', min_bytes=MIN_VOICE_CONFIG_BYTES)
    return model


def _runtime_import_die(exc):
    """A third-party import that failed -- numpy/soundfile at the top of main(),
    or a package (or one of ITS OWN dependencies) failing inside an engine
    constructor -- is "the audio runtime is incomplete", not "no voice engine
    installed": the engine itself may be correctly chosen and otherwise working
    (make_engine() might have already succeeded building it), just missing one
    supporting library the installer didn't provision. Names the actual missing
    module so this doesn't send someone down the "reinstall the engine" path when
    the fix is `pip install soundfile` in the state venv. Still exits 3 -- the
    remedy (run the installer) is the same either way -- but the message is
    deliberately distinct from make_engine()'s generic "not installed" one below,
    so the two failure modes are never confused for each other."""
    missing = getattr(exc, 'name', None) or str(exc)
    die(f"audio runtime incomplete (no module named '{missing}') — run: /podcast upgrade voice", 3)


def make_engine(engine_id, voices=None):
    """Builds the chosen engine's adapter, importing that engine's third-party
    package only now -- never on the --dry-run/--selftest path. `voices` (the
    resolved SPEAKER->voice-id mapping) lets an engine eagerly validate every
    voice it will actually be asked for, not just the first one some line happens
    to use. A failed import is reported via _runtime_import_die() (names the
    missing module); any OTHER failure building the engine -- a missing or
    undersized model file, a corrupt file onnxruntime itself refuses to load --
    becomes the generic "not installed" exit-3 message, since from the caller's
    point of view those mean "the weights aren't there yet". A broad
    `except Exception` for the non-import case (never a narrower tuple) is
    deliberate so a new failure mode in a third-party package can't slip through
    as a raw traceback."""
    try:
        if engine_id == 'kokoro-torch':
            return _make_kokoro_torch_engine()
        if engine_id == 'kokoro':
            return _make_kokoro_onnx_engine()
        if engine_id == 'piper':
            return _make_piper_engine(voices or {})
    except ImportError as e:
        _runtime_import_die(e)
    except Exception:
        pass
    die('no voice engine installed — run: /podcast upgrade voice', 3)


def _make_kokoro_torch_engine():
    import numpy as np
    from kokoro import KPipeline
    pipe = KPipeline(lang_code='a', repo_id=KOKORO_REPO_ID)
    sample_rate = ENGINE_DEFAULTS['kokoro-torch']['sample_rate']

    def synth(text, voice, speed):
        chunks = [a for _, _, a in pipe(text, voice=voice, speed=speed)]
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        return audio, sample_rate

    return _Engine('kokoro-torch', sample_rate, synth)


def _make_kokoro_onnx_engine():
    # Resolved (and size-checked) before importing kokoro_onnx, both so a missing/
    # undersized model fails fast without paying for the import, and so this half
    # of engine construction is testable under --selftest without kokoro_onnx
    # actually being installed.
    model_path, voices_path = _kokoro_model_paths()
    import numpy as np
    from kokoro_onnx import Kokoro
    kok = Kokoro(model_path, voices_path)

    def synth(text, voice, speed):
        samples, sr = kok.create(text, voice=voice, speed=speed, lang='en-us')
        return np.asarray(samples, dtype=np.float32), sr

    return _Engine('kokoro', ENGINE_DEFAULTS['kokoro']['sample_rate'], synth)


def _make_piper_engine(voices):
    # Resolve (and size-check) every voice this render will actually use, up
    # front and before importing piper -- so a voice whose .onnx/.onnx.json isn't
    # downloaded surfaces as the standard "not installed" exit right here, not as
    # a traceback raised from deep inside the first dialogue line that happens to
    # use it (this is HIGH1: a per-line lazy check would let MAYA render fine and
    # only blow up on ALEX's first line). Doing this before the piper import also
    # means it's testable under --selftest without the piper package installed.
    model_paths = {v: _piper_model_path(v) for v in set(voices.values())}
    import numpy as np
    from piper import PiperVoice, SynthesisConfig
    default_sr = ENGINE_DEFAULTS['piper']['sample_rate']
    loaded = {}

    def get_voice(voice_name):
        if voice_name not in loaded:
            loaded[voice_name] = PiperVoice.load(model_paths[voice_name])
        return loaded[voice_name]

    def synth(text, voice, speed):
        pv = get_voice(voice)
        # length_scale is a duration multiplier (bigger = slower), the inverse of
        # our speed knob (bigger speed = faster/shorter).
        syn_config = SynthesisConfig(length_scale=1.0 / speed if speed else 1.0)
        pieces, sr = [], default_sr
        for chunk in pv.synthesize(text, syn_config=syn_config):
            sr = chunk.sample_rate or sr
            pieces.append(np.asarray(chunk.audio_float_array, dtype=np.float32))
        audio = np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)
        return audio, sr

    return _Engine('piper', default_sr, synth)


def run_selftest():
    import tempfile
    import subprocess
    global CACHE_VERSION, TEMPLATES_DIR, _models_base, _make_piper_engine
    ok = True

    def check(name, cond):
        nonlocal ok
        print(('PASS' if cond else 'FAIL') + f'  {name}')
        if not cond:
            ok = False

    voices = {'MAYA': 'af_heart', 'ALEX': 'am_michael'}

    with tempfile.TemporaryDirectory() as td:
        script_path = os.path.join(td, 'script.txt')
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(
                "# comment, ignored\n"
                "\n"
                "# ── 1. Intro ──────\n"
                "MAYA: Hello there.\n"
                "ALEX: Hi Maya.\n"
                "---\n"
                "[pause 1.5]\n"
                "# ── 2. Middle ──────\n"
                "# ────────────────\n"
                "MAYA: The X-team met today.\n"
            )
        pattern, rules = load_lexicon(None)
        events, chapters = parse_script(script_path, voices, pattern, rules)
        check('parses speaker lines', events[0] == ('say', 'MAYA', 'Hello there.', 'Hello there.'))
        check('parses second speaker line', events[1][1:3] == ('ALEX', 'Hi Maya.'))
        check('--- becomes a segment pause', events[2] == ('pause', SEGMENT_GAP))
        check('[pause N] parses', events[3] == ('pause', 1.5))
        check('chapter headers recorded (2, divider-only header excluded)', len(chapters) == 2)
        check('chapter titles captured', [c[0] for c in chapters] == ['1. Intro', '2. Middle'])
        check('chapter 1 starts at event 0', chapters[0][1] == 0)
        check('chapter 2 starts at event 4 (after the pause)', chapters[1][1] == 4)
        check('a pure divider ("# ────") is not a chapter',
              CHAPTER_RE.match('# ────') is not None and not re.search(r'[^─\s]', CHAPTER_RE.match('# ────').group(1)))

        # Unknown speaker names the line number.
        bad_path = os.path.join(td, 'bad.txt')
        with open(bad_path, 'w', encoding='utf-8') as f:
            f.write("MAYA: fine.\nJUDY: not a known voice.\n")
        try:
            parse_script(bad_path, voices, pattern, rules)
            check('unknown speaker exits', False)
        except SystemExit as e:
            check('unknown speaker exits', True)
            check('unknown speaker error names line 2', str(e).startswith(f'{bad_path}:2:'))

        # [pause 1.2.3] is a clean error naming the line, not a crash.
        pause_path = os.path.join(td, 'badpause.txt')
        with open(pause_path, 'w', encoding='utf-8') as f:
            f.write("MAYA: hi\n[pause 1.2.3]\n")
        try:
            parse_script(pause_path, voices, pattern, rules)
            check('[pause 1.2.3] exits with a clean error', False)
        except SystemExit as e:
            check('[pause 1.2.3] exits with a clean error', True)
            check('bad pause error names line 2', str(e).startswith(f'{pause_path}:2:'))

        # Malformed --voices is a clear error, not a crash.
        try:
            parse_voices('MAYA=af_heart,ALEX')
            check('malformed --voices exits', False)
        except SystemExit as e:
            check('malformed --voices exits', True)
            check('malformed --voices exits with code 2', e.code == 2)
        check('well-formed --voices parses', parse_voices('MAYA=af_heart,ALEX=am_michael')
              == {'MAYA': 'af_heart', 'ALEX': 'am_michael'})

        # An explicitly-passed --lexicon that doesn't exist is an error; the implicit
        # default silently no-ops.
        missing = os.path.join(td, 'nope.txt')
        check('missing implicit-default lexicon is a silent no-op', load_lexicon(missing, explicit=False)[0] is None)
        try:
            load_lexicon(missing, explicit=True)
            check('missing explicit --lexicon exits', False)
        except SystemExit as e:
            check('missing explicit --lexicon exits', True)
            check('missing explicit --lexicon exits with code 2', e.code == 2)

        # Lexicon: whole word, longest-first, boundaries (including hyphen-adjacent), case-sensitive.
        lex_path = os.path.join(td, 'lex.txt')
        with open(lex_path, 'w', encoding='utf-8') as f:
            f.write(
                "# comment\n"
                "\n"
                "X-team => ex team\n"
                "X-team meeting => ex team gathering\n"
                "ceo => see e o\n"
                "Globex => Globex Corp\n"
                "not an arrow line\n"
                "dup => first\n"
                "dup => second\n"
            )
        import io, contextlib
        warn_buf = io.StringIO()
        with contextlib.redirect_stderr(warn_buf):
            pattern, rules = load_lexicon(lex_path)
        warnings = warn_buf.getvalue()
        check('malformed lexicon line (no "=>") warns with its line number', f'{lex_path}:7:' in warnings)
        check('duplicate written key warns which wins', 'dup' in warnings and 'second' in warnings)
        check('duplicate written key: last one wins', rules['dup'] == 'second')

        check('longest-first: multi-word rule wins',
              apply_lexicon('The X-team meeting starts now.', pattern, rules)
              == 'The ex team gathering starts now.')
        check('hyphen word-boundary: matches "the X-team."',
              apply_lexicon('the X-team.', pattern, rules) == 'the ex team.')
        check('hyphen word-boundary: does not match "the X-teams"',
              apply_lexicon('the X-teams', pattern, rules) == 'the X-teams')
        check('hyphen word-boundary: does not match "BX-team"',
              apply_lexicon('BX-team', pattern, rules) == 'BX-team')
        check('hyphen-ADJACENT match: "ex-Globex" is respelled',
              apply_lexicon('ex-Globex exec', pattern, rules) == 'ex-Globex Corp exec')
        check('hyphen-ADJACENT match: "Globex-style" would expose the trailing word too',
              apply_lexicon('Globex-style growth', pattern, rules) == 'Globex Corp-style growth')
        check('case-sensitive: "ceo" lowercase matches',
              apply_lexicon('the ceo spoke', pattern, rules) == 'the see e o spoke')
        check('case-sensitive: "CEO" uppercase does not match',
              apply_lexicon('the CEO spoke', pattern, rules) == 'the CEO spoke')
        check('missing lexicon file is a no-op', load_lexicon(os.path.join(td, 'nope2.txt'))[0] is None)

        # Dry-run duration-estimate arithmetic.
        est_events = [('say', 'MAYA', 'one two three four five', 'one two three four five'),
                      ('pause', 2.0),
                      ('say', 'ALEX', 'six seven eight', 'six seven eight')]
        total, starts = estimate_seconds(est_events)
        expected = (5 / WPM * 60.0) + 2.0 + (3 / WPM * 60.0)
        check('duration estimate matches manual arithmetic', abs(total - expected) < 1e-9)
        check('chapter start for first event is 0.0', starts[0] == 0.0)
        check('chapter start after pause accounts for speech + pause',
              abs(starts[2] - (5 / WPM * 60.0 + 2.0)) < 1e-9)

        # Cache key includes the trim/model version, so changing it invalidates old
        # entries -- mutate the real module constant and call the real cache_key()
        # (not a hand-rolled hash of two literals) so this actually exercises the
        # code path it claims to.
        orig_cache_version = CACHE_VERSION
        key_before_version_bump = cache_key('kokoro', 'af_heart', 24000, 1.0, 'hello')
        CACHE_VERSION = orig_cache_version + '-changed'
        key_after_version_bump = cache_key('kokoro', 'af_heart', 24000, 1.0, 'hello')
        CACHE_VERSION = orig_cache_version
        check('cache key changes when CACHE_VERSION changes (via the real cache_key(), '
              'not a hand-hashed literal)', key_before_version_bump != key_after_version_bump)

        # cache_key(): must fold in engine, voice, and sample rate -- switching any
        # one of the three must never collide with a different combination.
        base_key = cache_key('kokoro', 'af_heart', 24000, 1.0, 'hello there')
        check('cache key changes across engines (kokoro vs kokoro-torch)',
              base_key != cache_key('kokoro-torch', 'af_heart', 24000, 1.0, 'hello there'))
        check('cache key changes across voices',
              base_key != cache_key('kokoro', 'am_michael', 24000, 1.0, 'hello there'))
        check('cache key changes across sample rates',
              base_key != cache_key('kokoro', 'af_heart', 22050, 1.0, 'hello there'))
        check('cache key is stable for identical inputs',
              base_key == cache_key('kokoro', 'af_heart', 24000, 1.0, 'hello there'))
        # Mutation test, not a vacuous comparison against an unrelated hand-hashed
        # literal: actually bump ENGINE_CACHE_VERSION['piper'] and confirm cache_key()
        # moves for the exact same engine/voice/rate/speed/text. If the engine_version
        # term were ever dropped from cache_key(), this fails; the old version of this
        # check (comparing against a hardcoded 'piper-v0' hash) could not have caught
        # that, since it would "pass" no matter what cache_key() actually used.
        orig_piper_version = ENGINE_CACHE_VERSION['piper']
        key_before_engine_version_bump = cache_key('piper', 'voiceA', 22050, 1.0, 'hi')
        ENGINE_CACHE_VERSION['piper'] = orig_piper_version + '-mutated'
        key_after_engine_version_bump = cache_key('piper', 'voiceA', 22050, 1.0, 'hi')
        ENGINE_CACHE_VERSION['piper'] = orig_piper_version
        check("cache key folds in each engine's own ENGINE_CACHE_VERSION (mutating it "
              'actually moves the key)', key_before_engine_version_bump != key_after_engine_version_bump)

        # default_voices_for(): per-engine table, kokoro fallback for an unknown id.
        check('default voices for kokoro', default_voices_for('kokoro') == {'MAYA': 'af_heart', 'ALEX': 'am_michael'})
        check('default voices for piper differ from kokoro',
              default_voices_for('piper') != default_voices_for('kokoro'))
        check('unknown engine id falls back to kokoro defaults',
              default_voices_for('nonexistent-engine') == default_voices_for('kokoro'))

        # ---------------------------------------------------------------- casts
        def cast_text(body):
            return '# Cast: test\n\nprose a reader sees\n\n## Voices\n\n```cast\n' + body + '```\n\nmore prose\n'

        cv, cs, cp = parse_cast(cast_text('MODERATOR = bf_emma @ 0.98\nSKEPTIC = af_nicole\n'))
        check('cast: speakers and voices parsed',
              cv == {'MODERATOR': 'bf_emma', 'SKEPTIC': 'af_nicole'})
        check('cast: an @ speed is read', cs['MODERATOR'] == 0.98)
        check('cast: a speaker with no @ defaults to 1.0', cs['SKEPTIC'] == 1.0)

        cv3, _, _ = parse_cast(cast_text('A = af_heart\nB = am_michael\nC = bm_george\n'))
        check('cast: three speakers is not a special case', len(cv3) == 3)

        cv_c, cs_c, _ = parse_cast(cast_text(
            '# a comment line\n\nHOST = af_bella @ 1.02  # trailing comment\n'))
        check('cast: comments and blank lines are ignored',
              cv_c == {'HOST': 'af_bella'} and cs_c['HOST'] == 1.02)

        def cast_dies(body, label, whole=None):
            try:
                parse_cast(whole if whole is not None else cast_text(body))
            except SystemExit as e:
                check(label, e.code == 2)
            else:
                check(label, False)

        cast_dies(None, 'cast: a file with no ```cast block exits 2',
                  whole='# Cast: nope\n\njust prose, no block\n')
        cast_dies(None, 'cast: an unclosed ```cast block exits 2',
                  whole='```cast\nHOST = af_heart\n')
        cast_dies('', 'cast: an empty block exits 2')
        cast_dies('HOST af_heart\n', 'cast: a line with no = exits 2')
        cast_dies('HOST = \n', 'cast: a speaker with no voice exits 2')
        cast_dies('HOST = af_heart\nHOST = am_adam\n', 'cast: a duplicate speaker exits 2')
        cast_dies('HOST = af_heart @ fast\n', 'cast: a non-numeric speed exits 2')
        cast_dies('HOST = af_heart @ 10\n', 'cast: @ 10 (a typo for 1.0) exits 2')
        cast_dies('HOST = af_heart @ 0.1\n', 'cast: an absurdly slow speed exits 2')

        # parse_speeds()
        check('--speeds parses', parse_speeds('A=1.05,B=0.98') == {'A': 1.05, 'B': 0.98})
        for bad, label in (('A', 'no ='), ('A=x', 'not a number'), ('A=9', 'out of range')):
            try:
                parse_speeds(bad)
            except SystemExit as e:
                check(f'--speeds rejects {label}', e.code == 2)
            else:
                check(f'--speeds rejects {label}', False)

        # resolve_cast(): precedence and the pace fallback.
        class FakeArgs:
            def __init__(self, **kw):
                self.cast = self.voices = self.speeds = None
                self.speed = 1.0
                self.no_rotate = False
                self.exclude_voices = []
                self.__dict__.update(kw)

        v_def, s_def, _ = resolve_cast(FakeArgs(), 'kokoro')
        check('resolve_cast: no flags -> the engine default table',
              v_def == default_voices_for('kokoro'))
        check('resolve_cast: default table is paced at --speed',
              set(s_def.values()) == {1.0})
        check('resolve_cast: --speed becomes the baseline for every speaker',
              set(resolve_cast(FakeArgs(speed=1.1), 'kokoro')[1].values()) == {1.1})

        v_ov, _, _ = resolve_cast(FakeArgs(voices='MAYA=af_sky'), 'kokoro')
        check('resolve_cast: --voices alone still works (no cast)', v_ov['MAYA'] == 'af_sky')

        with tempfile.TemporaryDirectory() as td:
            cast_path = os.path.join(td, 'panel.md')
            with open(cast_path, 'w', encoding='utf-8') as f:
                f.write(cast_text('MODERATOR = bf_emma @ 0.98\nADVOCATE = am_michael @ 1.04\n'))
            v_c, s_c, p_c = resolve_cast(FakeArgs(cast=cast_path), 'kokoro')
            check('resolve_cast: --cast replaces the default table, it does not merge',
                  set(v_c) == {'MODERATOR', 'ADVOCATE'})
            check('resolve_cast: --cast carries its paces', s_c['ADVOCATE'] == 1.04)

            v_m, s_m, p_m = resolve_cast(
                FakeArgs(cast=cast_path, voices='ADVOCATE=am_adam', speeds='MODERATOR=1.0'), 'kokoro')
            check('resolve_cast: --voices overrides one cast voice, keeps the rest',
                  v_m == {'MODERATOR': 'bf_emma', 'ADVOCATE': 'am_adam'})
            check('resolve_cast: --speeds overrides one cast pace, keeps the rest',
                  s_m['MODERATOR'] == 1.0 and s_m['ADVOCATE'] == 1.04)

            try:
                resolve_cast(FakeArgs(cast=os.path.join(td, 'missing.md')), 'kokoro')
            except SystemExit as e:
                check('resolve_cast: a missing --cast file exits 2', e.code == 2)
            else:
                check('resolve_cast: a missing --cast file exits 2', False)

        # ------------------------------------------------------- rotation pools
        pv2, ps2, pp2 = parse_cast(cast_text('HOST = bf_lily, af_aoede, bm_george @ 0.98\n'))
        check('cast: a comma list becomes a rotation pool',
              pp2['HOST'] == ['bf_lily', 'af_aoede', 'bm_george'])
        check('cast: the first pool entry is the slot default', pv2['HOST'] == 'bf_lily')
        check('cast: one pace applies to the whole pool', ps2['HOST'] == 0.98)
        check('cast: a single voice is a pool of one',
              parse_cast(cast_text('HOST = af_heart\n'))[2]['HOST'] == ['af_heart'])
        cast_dies('HOST = af_heart, af_heart\n', 'cast: the same voice twice in one pool exits 2')

        pools3 = {'HOST': ['a', 'b', 'c']}
        check('rotation: with no history, the first voice is taken',
              choose_voices(pools3)['HOST'] == 'a')
        check('rotation: the least recently used voice is next',
              choose_voices(pools3, {'HOST': ['a']})['HOST'] == 'b')
        check('rotation: history of two moves to the third',
              choose_voices(pools3, {'HOST': ['a', 'b']})['HOST'] == 'c')
        check('rotation: a full cycle wraps to the oldest',
              choose_voices(pools3, {'HOST': ['a', 'b', 'c']})['HOST'] == 'a')
        check('rotation: order is by recency, not by pool position',
              choose_voices(pools3, {'HOST': ['b', 'c', 'a']})['HOST'] == 'b')
        check('rotation: --no-rotate always takes the default',
              choose_voices(pools3, {'HOST': ['a', 'b']}, rotate=False)['HOST'] == 'a')
        check('rotation: history naming a voice no longer in the pool is ignored',
              choose_voices(pools3, {'HOST': ['gone', 'a']})['HOST'] == 'b')

        check('blocklist: a blocked voice is never chosen',
              choose_voices(pools3, {}, blocked=['a'])['HOST'] == 'b')
        check('blocklist: blocking cascades to the next available',
              choose_voices(pools3, {}, blocked=['a', 'b'])['HOST'] == 'c')
        check('blocklist: whitespace and empties in the list are ignored',
              choose_voices(pools3, {}, blocked=[' a ', '', None])['HOST'] == 'b')
        try:
            choose_voices(pools3, {}, blocked=['a', 'b', 'c'])
        except SystemExit as e:
            check('blocklist: blocking a whole slot exits 2 with a fixable message', e.code == 2)
        else:
            check('blocklist: blocking a whole slot exits 2 with a fixable message', False)

        multi = choose_voices({'HOST': ['a', 'b'], 'GUEST': ['x', 'y']}, {'HOST': ['a']})
        check('rotation: each slot rotates independently',
              multi == {'HOST': 'b', 'GUEST': 'x'})

        # record_rotation(): history is most-recent-last and bounded.
        h1 = record_rotation({}, {'HOST': 'a'})
        check('history: a first pick is recorded', h1 == {'HOST': ['a']})
        h2 = record_rotation(h1, {'HOST': 'b'})
        check('history: the newest pick goes last', h2['HOST'] == ['a', 'b'])
        h3 = record_rotation(h2, {'HOST': 'a'})
        check('history: re-picking a voice moves it to the end, not duplicated',
              h3['HOST'] == ['b', 'a'])
        long_hist = {'HOST': [str(i) for i in range(12)]}
        check('history: is trimmed to the keep window',
              len(record_rotation(long_hist, {'HOST': 'new'}, keep=8)['HOST']) == 8)
        check('history: other slots are left alone',
              record_rotation({'A': ['1'], 'B': ['2']}, {'A': '3'})['B'] == ['2'])

        # Per-speaker pace must reach the cache key, or two speakers at different
        # paces would serve each other's audio for the same line.
        check('cache key separates two paces of one voice+line',
              cache_key('kokoro', 'af_heart', 24000, 1.0, 'same words')
              != cache_key('kokoro', 'af_heart', 24000, 1.05, 'same words'))

        # ------------------------------------------------- metadata + chapters
        check('title from a slug', title_from_out('/x/learning-to-sail.mp3') == 'Learning To Sail')
        check('title keeps an acronym', title_from_out('/x/NATO-explained.mp3') == 'NATO Explained')

        meta = build_ffmetadata({'title': 'T', 'artist': 'A', 'album': None},
                                [{'title': 'One', 'start': 0.0}, {'title': 'Two', 'start': 12.5}], 30.0)
        check('ffmetadata starts with the magic line', meta.startswith(';FFMETADATA1\n'))
        check('ffmetadata writes set tags', 'title=T' in meta and 'artist=A' in meta)
        check('ffmetadata omits empty tags', 'album=' not in meta)
        check('ffmetadata writes one [CHAPTER] per record', meta.count('[CHAPTER]') == 2)
        check('ffmetadata chapter 1 spans to chapter 2',
              'START=0' in meta and 'END=12500' in meta)
        check('ffmetadata last chapter ends at the duration', 'END=30000' in meta)
        check('ffmetadata chapter titles are written', 'title=One' in meta and 'title=Two' in meta)

        # A chapter list with a zero-length entry is dropped wholesale by ffmpeg.
        meta_dup = build_ffmetadata({}, [{'title': 'A', 'start': 5.0}, {'title': 'B', 'start': 5.0}], 5.0)
        starts_ends = [l for l in meta_dup.splitlines() if l.startswith(('START=', 'END='))]
        check('ffmetadata never emits a zero-length chapter',
              all(int(e.split('=')[1]) > int(s.split('=')[1])
                  for s, e in zip(starts_ends[::2], starts_ends[1::2])))
        check('ffmetadata escapes the characters that would reparse',
              '\\=' in build_ffmetadata({'title': 'a=b'}, [], 1.0))
        check('ffmetadata with no chapters is still valid',
              build_ffmetadata({'title': 'T'}, [], 1.0).strip().endswith('title=T'))

        # Every cast this skill ships must parse, and its voices must be ones the
        # default engine actually has. A typo here reaches every user and surfaces
        # only mid-render, after the research has been paid for.
        shipped = sorted(glob.glob(os.path.join(CASTS_DIR, '*.md'))) if os.path.isdir(CASTS_DIR) else []
        cast_files = [f for f in shipped
                      if open(f, encoding='utf-8').read().lstrip().startswith('# Cast:')]
        check('casts/ ships at least the three documented casts', len(cast_files) >= 3)
        # The prose docs in casts/ must not be mistaken for casts, and every file
        # that isn't a doc must be one -- so a new cast can't be added without the
        # "# Cast:" header that makes it discoverable.
        docs = {'README.md', 'VOICES.md'}
        check('casts/ ships its prose docs and they are not parsed as casts',
              docs <= {os.path.basename(f) for f in shipped}
              and len(cast_files) == len(shipped) - len(docs))
        for path in cast_files:
            name = os.path.basename(path)
            try:
                cvoices, cspeeds, cpools = parse_cast(open(path, encoding='utf-8').read(), path)
            except SystemExit:
                check(f'shipped cast parses: {name}', False)
                continue
            check(f'shipped cast parses: {name}', bool(cvoices))
            check(f'shipped cast {name}: every voice is in the kokoro pack',
                  all(v in KOKORO_VOICE_IDS for v in cvoices.values()))
            check(f'shipped cast {name}: paces stay in the believable band',
                  all(0.9 <= sp <= 1.15 for sp in cspeeds.values()))
            check(f'shipped cast {name}: no two speakers share a voice',
                  len(set(cvoices.values())) == len(cvoices))
        panel = os.path.join(CASTS_DIR, 'panel.md')
        if os.path.exists(panel):
            pv, _, ppools = parse_cast(open(panel, encoding='utf-8').read(), panel)
            check('panel is the three-voice cast the debate angle expects',
                  set(pv) == {'HOST', 'ADVOCATE', 'SKEPTIC'})
            # Two same-accent, same-gender voices in one episode is the classic
            # mistake -- a listener cannot tell who is talking.
            check('panel voices differ in accent or gender',
                  len({v[:2] for v in pv.values()}) >= 2)
        check('the debate angle ships alongside the panel cast',
              os.path.exists(os.path.join(REPO_ROOT, 'angles', 'debate.md')))

        # select_engine(): precedence is --engine > config voice_engine > config
        # detect() > exit 3. A fake config object is injected via `which_config` so
        # this doesn't depend on the real config module being installed.
        class FakeConfig:
            def __init__(self, load_result=None, detect_result=None, raise_load=False, raise_detect=False):
                self._load, self._detect = load_result or {}, detect_result or {}
                self._raise_load, self._raise_detect = raise_load, raise_detect

            def load(self):
                if self._raise_load:
                    raise RuntimeError('boom')
                return self._load

            def detect(self):
                if self._raise_detect:
                    raise RuntimeError('boom')
                return self._detect

        check('--engine flag wins over everything',
              select_engine('piper', which_config=FakeConfig({'voice_engine': 'kokoro'})) == 'piper')
        check("config voice_engine wins when --engine isn't passed",
              select_engine(None, which_config=FakeConfig({'voice_engine': 'kokoro-torch'},
                                                            {'voice_active': 'piper'})) == 'kokoro-torch')
        check('config.detect() is used when voice_engine is unset',
              select_engine(None, which_config=FakeConfig({}, {'voice_active': 'piper'})) == 'piper')
        check('voice_engine="auto" (config.py\'s own DEFAULTS sentinel) falls through to detect(), '
              'is not treated as a literal engine id',
              select_engine(None, which_config=FakeConfig({'voice_engine': 'auto'},
                                                            {'voice_active': 'kokoro'})) == 'kokoro')
        check('voice_engine="none" also falls through to detect() rather than being returned literally',
              select_engine(None, which_config=FakeConfig({'voice_engine': 'none'},
                                                            {'voice_active': 'piper'})) == 'piper')
        check('a raising config.load() falls through to detect() rather than crashing',
              select_engine(None, which_config=FakeConfig(raise_load=True,
                                                            detect_result={'voice_active': 'kokoro'})) == 'kokoro')
        try:
            select_engine(None, which_config=FakeConfig({}, {'voice_active': None}))
            check('no engine anywhere (config present, nothing active) exits', False)
        except SystemExit as e:
            check('no engine anywhere (config present, nothing active) exits', True)
            check('...with exit code 3 (distinct from a gate/tool error)', e.code == 3)
        try:
            select_engine(None, which_config=FakeConfig(raise_load=True, raise_detect=True))
            check('a config that raises on both load() and detect() still exits cleanly', False)
        except SystemExit as e:
            check('a config that raises on both load() and detect() still exits cleanly', True)
            check('...with exit code 3', e.code == 3)
        try:
            select_engine(None, which_config=None)
            check('no config module at all (bare checkout) exits', False)
        except SystemExit as e:
            check('no config module at all (bare checkout) exits', True)
            check('...with exit code 3', e.code == 3)

        # LOW 7: an unvalidated config value (e.g. PODCAST_VOICE_ENGINE=Kokoro, wrong
        # case) must not silently masquerade as "nothing installed" -- it should name
        # the bad value.
        err_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(err_buf):
                select_engine(None, which_config=FakeConfig({'voice_engine': 'Kokoro'}))
            check('an unknown engine name from config exits rather than being returned', False)
        except SystemExit as e:
            check('an unknown engine name from config exits rather than being returned', True)
            check('...with a message naming the bad value', 'Kokoro' in err_buf.getvalue())
            check('...and exit code 2 (a bad config value, not "nothing installed")', e.code == 2)

        # resolve_ffmpeg: config-supplied absolute path (a bundled, sudo-free copy)
        # wins over the bare PATH-resolved name; absent config, the fallback is
        # exactly what this script always shot at before ffmpeg resolution existed.
        check('resolve_ffmpeg: uses the config-supplied absolute path when config has one',
              resolve_ffmpeg(which_config=FakeConfig(detect_result={'ffmpeg': '/state/bin/ffmpeg'}))
              == '/state/bin/ffmpeg')
        check('resolve_ffmpeg: falls back to the bare name on PATH when config is absent',
              resolve_ffmpeg(which_config=None) == 'ffmpeg')
        check('resolve_ffmpeg: falls back to the bare name when config has nothing for it',
              resolve_ffmpeg(which_config=FakeConfig(detect_result={})) == 'ffmpeg')
        check('resolve_ffmpeg: a raising config.detect() falls back to the bare name rather than crashing',
              resolve_ffmpeg(which_config=FakeConfig(raise_detect=True)) == 'ffmpeg')

        # The three "can't render" exit-3 messages must all be textually distinct
        # from one another -- a missing ffmpeg binary is neither "no voice engine"
        # nor "audio runtime incomplete", and must not be confused with either.
        ffmpeg_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(ffmpeg_buf):
                die('ffmpeg not found — run: /podcast upgrade audio', 3)
        except SystemExit:
            pass
        no_engine_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(no_engine_buf):
                die('no voice engine installed — run: /podcast upgrade voice', 3)
        except SystemExit:
            pass
        runtime_incomplete_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(runtime_incomplete_buf):
                _runtime_import_die(ModuleNotFoundError("No module named 'soundfile'", name='soundfile'))
        except SystemExit:
            pass
        three_messages = {ffmpeg_buf.getvalue(), no_engine_buf.getvalue(), runtime_incomplete_buf.getvalue()}
        check('the ffmpeg-missing, no-voice-engine, and runtime-incomplete messages '
              'are all three textually distinct', len(three_messages) == 3)
        check('...the ffmpeg message names ffmpeg specifically',
              'ffmpeg' in ffmpeg_buf.getvalue() and 'ffmpeg' not in no_engine_buf.getvalue()
              and 'ffmpeg' not in runtime_incomplete_buf.getvalue())

        # LOW 8: an output path ending .wav collides with this render's own
        # intermediate WAV (ffmpeg would read and write the same file).
        wav_out = os.path.join(td, 'episode.wav')
        r = subprocess.run([sys.executable, __file__, script_path, wav_out],
                            capture_output=True, text=True)
        check('an output path ending .wav is rejected rather than corrupting silently',
              r.returncode == 2 and '.wav' in r.stderr)

        # HIGH 1: _make_piper_engine must validate EVERY configured voice up front,
        # not just whichever one the first dialogue line happens to use. Runs without
        # the piper package installed, since the eager check now happens before the
        # `from piper import ...` line.
        piper_models = os.path.join(td, 'piper-models', 'piper')
        os.makedirs(piper_models)
        good_voice = os.path.join(piper_models, 'good-voice.onnx')
        with open(good_voice, 'wb') as f:
            f.write(b'x' * (MIN_MODEL_BYTES + 1))
        with open(good_voice + '.json', 'w', encoding='utf-8') as f:
            f.write('{}')
        orig_models_base = _models_base
        _models_base = lambda: os.path.dirname(piper_models)
        try:
            _make_piper_engine({'MAYA': 'good-voice', 'ALEX': 'missing-voice'})
            check('_make_piper_engine eagerly validates every configured voice, not just the first', False)
        except FileNotFoundError as e:
            check('_make_piper_engine eagerly validates every configured voice, not just the first', True)
            check('...naming the missing voice specifically', 'missing-voice' in str(e))
        finally:
            _models_base = orig_models_base

        # MED 9 (part 1): _check_model_file rejects a present-but-undersized/corrupt
        # file (0 bytes, a truncated download, an HTML error page saved under the
        # expected name) rather than letting onnxruntime/piper raise 30 lines deep.
        tiny_path = os.path.join(td, 'tiny.onnx')
        with open(tiny_path, 'wb') as f:
            f.write(b'x' * 10)
        try:
            _check_model_file(tiny_path)
            check('_check_model_file rejects an undersized/corrupt file', False)
        except FileNotFoundError as e:
            check('_check_model_file rejects an undersized/corrupt file', True)
            check('...naming the actual size in the message', '10 bytes' in str(e))
        big_path = os.path.join(td, 'big.onnx')
        with open(big_path, 'wb') as f:
            f.write(b'x' * (MIN_MODEL_BYTES + 1))
        check('_check_model_file accepts a big-enough file', _check_model_file(big_path) is None)

        # MED 9 (part 2): a 0-byte kokoro model gives a clean exit 3 through the real
        # make_engine(), not a raw traceback -- and this must work even without
        # kokoro_onnx installed, since the size check now happens before that import.
        kokoro_models = os.path.join(td, 'kokoro-models', 'kokoro')
        os.makedirs(kokoro_models)
        with open(os.path.join(kokoro_models, 'kokoro-v1.0.onnx'), 'wb') as f:
            pass  # 0 bytes
        with open(os.path.join(kokoro_models, 'voices-v1.0.bin'), 'wb') as f:
            f.write(b'x' * (MIN_MODEL_BYTES + 1))
        _models_base = lambda: os.path.dirname(kokoro_models)
        try:
            make_engine('kokoro', {})
            check('a 0-byte kokoro model gives a clean exit 3, not a traceback', False)
        except SystemExit as e:
            check('a 0-byte kokoro model gives a clean exit 3, not a traceback', True)
            check('...with exit code 3', e.code == 3)
        finally:
            _models_base = orig_models_base

        # Runtime-incomplete vs engine-missing: two different failure modes that
        # must never collapse into an indistinguishable message. A real repro: a
        # piper install with no soundfile makes the top-level numpy/soundfile
        # import in main() fail even though make_engine('piper', ...) itself would
        # have succeeded -- that must say "audio runtime incomplete", not "no
        # voice engine installed".
        runtime_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(runtime_buf):
                _runtime_import_die(ModuleNotFoundError("No module named 'soundfile'", name='soundfile'))
            check('_runtime_import_die exits', False)
        except SystemExit as e:
            check('_runtime_import_die exits', True)
            check('...with exit code 3 (same upgrade remedy as "no voice engine installed")', e.code == 3)
            check('...naming the actual missing module', 'soundfile' in runtime_buf.getvalue())
            check('...saying "audio runtime incomplete", not "no voice engine installed"',
                  'audio runtime incomplete' in runtime_buf.getvalue()
                  and 'no voice engine installed' not in runtime_buf.getvalue())

        engine_missing_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(engine_missing_buf):
                die('no voice engine installed — run: /podcast upgrade voice', 3)
        except SystemExit:
            pass
        check('the two messages are textually distinct (different code paths, must stay '
              "distinguishable, not just different exit codes -- there aren't any here)",
              runtime_buf.getvalue() != engine_missing_buf.getvalue())

        # make_engine() itself: an ImportError from inside an engine constructor
        # (the package -- or one of ITS dependencies -- missing) gets the same
        # distinct runtime-incomplete treatment; a non-import failure (missing/
        # corrupt model file) still gets the generic "not installed" message. The
        # constructor is monkeypatched so this is deterministic regardless of
        # whether piper is actually installed on the machine running --selftest.
        orig_make_piper_engine = _make_piper_engine

        def _boom_import(voices):
            raise ImportError("No module named 'piper'", name='piper')
        _make_piper_engine = _boom_import
        buf_a = io.StringIO()
        try:
            with contextlib.redirect_stderr(buf_a):
                make_engine('piper', {})
            check('make_engine: an ImportError from an engine constructor names the missing module', False)
        except SystemExit as e:
            check('make_engine: an ImportError from an engine constructor names the missing module', True)
            check('...naming it', 'piper' in buf_a.getvalue())
            check('...as "audio runtime incomplete", not "no voice engine installed"',
                  'audio runtime incomplete' in buf_a.getvalue())
            check('...still exit 3', e.code == 3)
        finally:
            _make_piper_engine = orig_make_piper_engine

        def _boom_filenotfound(voices):
            raise FileNotFoundError('/no/such/model.onnx')
        _make_piper_engine = _boom_filenotfound
        buf_b = io.StringIO()
        try:
            with contextlib.redirect_stderr(buf_b):
                make_engine('piper', {})
            check('make_engine: a non-import failure (missing model file) keeps the generic message', False)
        except SystemExit as e:
            check('make_engine: a non-import failure (missing model file) keeps the generic message', True)
            check('...says "no voice engine installed", not "audio runtime incomplete"',
                  'no voice engine installed' in buf_b.getvalue()
                  and 'audio runtime incomplete' not in buf_b.getvalue())
            check('...still exit 3', e.code == 3)
        finally:
            _make_piper_engine = orig_make_piper_engine

        # HIGH 3: default lexicon path prefers the episode's own copy, falls back to
        # the skill's templates/ copy, and --help documents where it looks.
        ep_dir = os.path.join(td, 'episode-with-lexicon')
        os.makedirs(ep_dir)
        own_lexicon = os.path.join(ep_dir, 'lexicon.txt')
        with open(own_lexicon, 'w', encoding='utf-8') as f:
            f.write('X-team => ex team\n')
        ep_script = os.path.join(ep_dir, 'ep-script.txt')
        with open(ep_script, 'w', encoding='utf-8') as f:
            f.write('MAYA: hi\n')
        check("default_lexicon_path prefers the episode's own lexicon.txt",
              default_lexicon_path(ep_script) == own_lexicon)

        bare_dir = os.path.join(td, 'episode-without-lexicon')
        os.makedirs(bare_dir)
        bare_script = os.path.join(bare_dir, 'bare-script.txt')
        with open(bare_script, 'w', encoding='utf-8') as f:
            f.write('MAYA: hi\n')
        expected_template = os.path.join(TEMPLATES_DIR, 'lexicon.txt')
        check('default_lexicon_path falls back to the skill templates/lexicon.txt '
              'when the episode has none',
              os.path.exists(expected_template) and default_lexicon_path(bare_script) == expected_template)

        orig_templates_dir = TEMPLATES_DIR
        TEMPLATES_DIR = os.path.join(td, 'no-such-templates-dir')
        check('default_lexicon_path with neither an episode nor a template lexicon still '
              "returns the episode path (load_lexicon()'s existing silent no-op handles it)",
              default_lexicon_path(bare_script) == os.path.join(bare_dir, 'lexicon.txt'))
        TEMPLATES_DIR = orig_templates_dir

        check('--lexicon --help documents the default lookup order',
              'templates/lexicon.txt' in build_arg_parser().format_help())

        # HIGH 2: re-exec decision logic (never actually exec's -- _reexec_target()
        # is pure, tested in isolation from maybe_reexec_into_venv()'s os.execve).
        check('_needs_reexec is False when every needed module imports fine',
              _needs_reexec('kokoro', check_fn=lambda m: True) is False)
        check('_needs_reexec is True when any needed module (including the engine '
              "package) can't be imported",
              _needs_reexec('piper', check_fn=lambda m: m != 'piper') is True)

        class FakeVenvConfig:
            def __init__(self, venv_python):
                self._venv = venv_python

            def venv_python(self):
                return self._venv

        always_needs, never_needs = (lambda engine_id: True), (lambda engine_id: False)
        check('_reexec_target: no re-exec needed -> None',
              _reexec_target('kokoro', which_config=FakeVenvConfig('/some/venv/python'), env={},
                              needs_reexec_fn=never_needs) is None)
        check('_reexec_target: PODCAST_REEXEC=1 blocks a second re-exec (loop guard)',
              _reexec_target('kokoro', which_config=FakeVenvConfig('/some/venv/python'),
                              env={'PODCAST_REEXEC': '1'}, needs_reexec_fn=always_needs) is None)
        check('_reexec_target: no config at all -> None (falls through to the normal exit-3 path)',
              _reexec_target('kokoro', which_config=None, env={}, needs_reexec_fn=always_needs) is None)
        check('_reexec_target: a configured venv_python that does not exist on disk -> None',
              _reexec_target('kokoro', which_config=FakeVenvConfig('/no/such/venv/python'), env={},
                              needs_reexec_fn=always_needs) is None)
        check('_reexec_target: never targets the CURRENT interpreter (a no-op re-exec)',
              _reexec_target('kokoro', which_config=FakeVenvConfig(sys.executable), env={},
                              needs_reexec_fn=always_needs) is None)

        # Regression: a venv's python is typically a symlink to (or copy of) the same
        # base interpreter binary as system python3 -- realpath-equality would wrongly
        # treat that as "already in the venv" and refuse to re-exec into it at all.
        symlinked_venv_python = os.path.join(td, 'venv-python-symlink')
        try:
            os.symlink(os.path.realpath(sys.executable), symlinked_venv_python)
            check('_reexec_target: a venv python that is a symlink to the same real '
                  'binary as the CURRENT interpreter is still a valid re-exec target '
                  '(distinct path, not a no-op)',
                  _reexec_target('kokoro', which_config=FakeVenvConfig(symlinked_venv_python), env={},
                                  needs_reexec_fn=always_needs) == symlinked_venv_python)
        except (OSError, NotImplementedError):
            pass  # symlinks unavailable on this filesystem -- not what this checks anyway

        fake_venv_python = os.path.join(td, 'fake-venv-python3')
        with open(fake_venv_python, 'w', encoding='utf-8') as f:
            f.write('#!/bin/sh\n')
        os.chmod(fake_venv_python, 0o755)
        check('_reexec_target: names a different, existing venv interpreter when needed',
              _reexec_target('kokoro', which_config=FakeVenvConfig(fake_venv_python), env={},
                              needs_reexec_fn=always_needs) == fake_venv_python)

        # atomic_write: the primitive behind the cache-write fix (kill -9 mid-write /
        # concurrent renderers must never see a partial file at the real path).
        # Exercised here with plain text so it runs under system python3, same code
        # path the real WAV writes use.
        target = os.path.join(td, 'atomic-target.bin')
        atomic_write(target, lambda tmp: open(tmp, 'w', encoding='utf-8').write('hello'))
        check('atomic_write: successful write lands at the real path',
              os.path.exists(target) and open(target, encoding='utf-8').read() == 'hello')
        check('atomic_write: no leftover tmp file after success',
              not any(n.startswith('atomic-target.bin.tmp-') for n in os.listdir(td)))

        target2 = os.path.join(td, 'atomic-target2.bin')

        def boom(tmp):
            open(tmp, 'w', encoding='utf-8').write('partial')
            raise RuntimeError('simulated kill mid-write')
        try:
            atomic_write(target2, boom)
        except RuntimeError:
            pass
        check('atomic_write: a failed write never creates the real path', not os.path.exists(target2))
        check('atomic_write: no leftover tmp file after a failed write',
              not any(n.startswith('atomic-target2.bin.tmp-') for n in os.listdir(td)))

        target3 = os.path.join(td, 'atomic-target3.bin')
        with open(target3, 'w', encoding='utf-8') as f:
            f.write('old-complete-content')
        seen_during_write = {}

        def slow_write(tmp):
            open(tmp, 'w', encoding='utf-8').write('new-content')
            seen_during_write['target_during'] = open(target3, encoding='utf-8').read()
        atomic_write(target3, slow_write)
        check('atomic_write: readers see the OLD complete file while the new one is being written',
              seen_during_write['target_during'] == 'old-complete-content')
        check('atomic_write: the real path has the new content once replace happens',
              open(target3, encoding='utf-8').read() == 'new-content')

        # pid_alive
        check('pid_alive is True for our own running process', pid_alive(os.getpid()) is True)
        check('pid_alive is False for a pid that does not exist', pid_alive(2**30 - 1) is False)

        # cleanup_orphan_tmp_files: never a blanket sweep -- only age>1h OR dead pid.
        cache_td = os.path.join(td, 'cache')
        os.makedirs(cache_td)

        def mk_tmp(name, age_seconds):
            p = os.path.join(cache_td, name)
            open(p, 'w', encoding='utf-8').write('partial')
            t = time.time() - age_seconds
            os.utime(p, (t, t))
            return p

        recent_alive = mk_tmp(f'abc.wav.tmp-{os.getpid()}', 5)
        recent_dead = mk_tmp('abc.wav.tmp-999999999', 5)
        old_alive = mk_tmp(f'def.wav.tmp-{os.getpid()}', ORPHAN_TMP_MAX_AGE + 5)
        old_dead = mk_tmp('def.wav.tmp-999999999', ORPHAN_TMP_MAX_AGE + 5)
        not_a_tmp = os.path.join(cache_td, 'realfile.wav')
        open(not_a_tmp, 'w', encoding='utf-8').write('a real cache entry')
        cleanup_orphan_tmp_files(cache_td, is_alive=lambda pid: pid == os.getpid())
        check('recent tmp file owned by a LIVE pid is left alone (a concurrent render)',
              os.path.exists(recent_alive))
        check('recent tmp file owned by a DEAD pid is removed', not os.path.exists(recent_dead))
        check('old tmp file owned by a live pid is removed anyway (age alone is enough)',
              not os.path.exists(old_alive))
        check('old tmp file owned by a dead pid is removed', not os.path.exists(old_dead))
        check('a real (non-tmp) cache file is never touched by cleanup', os.path.exists(not_a_tmp))

    return 0 if ok else 1


ENGINE_PACKAGE = {'kokoro-torch': 'kokoro', 'kokoro': 'kokoro_onnx', 'piper': 'piper'}


def _importable(module_name):
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def _needs_reexec(engine_id, check_fn=_importable):
    """True if THIS interpreter can't import what an actual render needs: numpy/
    soundfile always, plus the chosen engine's own package. `check_fn` is
    injectable (selftest) so this is testable without depending on what's
    actually installed on the machine running --selftest."""
    mods = ['numpy', 'soundfile', ENGINE_PACKAGE.get(engine_id)]
    return not all(check_fn(m) for m in mods if m)


def _reexec_target(engine_id, which_config=_UNSET, env=None, needs_reexec_fn=_needs_reexec):
    """Pure decision, no exec: returns the venv python path to re-exec into, or
    None if no re-exec is needed or possible. Kept separate from
    maybe_reexec_into_venv() so --selftest can verify every branch of this logic
    without ever replacing the test process. `env` defaults to the real
    os.environ; tests pass a plain dict instead."""
    env = os.environ if env is None else env
    if env.get('PODCAST_REEXEC') == '1':
        # Already re-exec'd once -- if the venv interpreter is somehow missing the
        # package too, that's left to fall through to the normal "no voice engine
        # installed" exit further down, not another exec (would loop forever).
        return None
    if not needs_reexec_fn(engine_id):
        return None
    cfg = config if which_config is _UNSET else which_config
    if not cfg:
        return None
    try:
        venv_python = cfg.venv_python()
    except Exception:
        venv_python = None
    if not venv_python or not os.path.exists(venv_python):
        return None
    # Plain path comparison, NOT realpath: a venv's python is typically a symlink
    # (or copy) of the base system interpreter, so its realpath often equals the
    # system python's realpath even though it's a materially different interpreter
    # (its own sys.prefix/site-packages) -- resolving symlinks here would wrongly
    # treat "not yet in the venv" as "already in the venv" and refuse to re-exec.
    # A straight abspath comparison still correctly recognizes the post-re-exec
    # case (sys.executable then IS venv_python, verbatim) and the case where
    # someone invoked the venv's own python directly in the first place.
    if os.path.abspath(venv_python) == os.path.abspath(sys.executable):
        return None
    return venv_python


def maybe_reexec_into_venv(engine_id):
    """setup.sh installs numpy/soundfile/the engine packages into config.venv_python()'s
    site-packages, not the system interpreter's -- so the documented `python3
    render.py ...` invocation would otherwise die with a raw ModuleNotFoundError.
    If _reexec_target() names a different, working venv interpreter, re-exec into
    it now (os.execve, same argv) -- never returns on success."""
    target = _reexec_target(engine_id)
    if not target:
        return
    env = dict(os.environ)
    env['PODCAST_REEXEC'] = '1'
    os.execve(target, [target] + sys.argv, env)  # pragma: no cover (replaces process)


def main():
    ap = build_arg_parser()
    args = ap.parse_args()

    if args.selftest:
        sys.exit(run_selftest())

    if not args.script:
        ap.error('the following arguments are required: script')

    if args.dry_run:
        # No real engine is resolved for a dry run: every engine's default table
        # uses the same speaker keys (MAYA/ALEX), so parsing the script for its
        # word/duration estimate never needs to know which engine would render it.
        # No real engine is resolved for a dry run, so the cast is resolved against
        # kokoro's table -- only the speaker KEYS matter for parsing the script.
        voices, speeds, _pools = resolve_cast(args, 'kokoro')
        engine_id = None
    else:
        if not args.out:
            ap.error('the following arguments are required: out')
        if args.out.lower().endswith('.wav'):
            # The render pipeline writes its own intermediate WAV at
            # os.path.splitext(out)[0] + '.wav', then has ffmpeg read that path and
            # write OUT -- if OUT already ends in .wav those are the same file, so
            # ffmpeg would be asked to read and write it at once (undefined result,
            # usually a truncated/corrupt file). Reject up front with a clear message
            # rather than let that happen silently.
            die(f'{args.out}: output must not end in .wav (it collides with this '
                f'render\'s own intermediate file) -- use .mp3', 2)
        engine_id = select_engine(args.engine)
        voices, speeds, pools = resolve_cast(args, engine_id)
        # A blocklist is a standing preference ("never that voice"), so it lives in
        # config; --exclude-voices adds to it for one run.
        try:
            args.exclude_voices = list(dict.fromkeys(
                list(args.exclude_voices) + parse_voices_list(config.load().get('voice_blocklist'))))
        except Exception:
            pass

    lexicon_explicit = args.lexicon is not None
    lexicon_path = args.lexicon if lexicon_explicit else default_lexicon_path(args.script)
    pattern, rules = load_lexicon(lexicon_path, explicit=lexicon_explicit)
    events, chapters = parse_script(args.script, voices, pattern, rules)

    if args.dry_run:
        total, starts = estimate_seconds(events)
        say_lines = [e for e in events if e[0] == 'say']
        word_count = sum(len(e[3].split()) for e in say_lines)
        print(f'{len(say_lines)} dialogue lines, {word_count} spoken words')
        print(f'estimated duration: {fmt_mmss(total)} ({total / 60:.1f} min) at {WPM} wpm + gaps')
        if chapters:
            print('chapters:')
            for title, idx in chapters:
                print(f'  {fmt_mmss(starts[idx])}  {title}')
        else:
            print('chapters: none')
        return

    # If this interpreter can't satisfy what's about to be imported but the
    # installer's venv can, re-exec into it now (never returns on success) --
    # kept below the dry-run/selftest exits so both still run under bare system
    # python3 with zero third-party packages.
    maybe_reexec_into_venv(engine_id)

    try:
        import numpy as np
        import soundfile as sf
    except ImportError as e:
        # Distinct from make_engine()'s "no voice engine installed": the chosen
        # engine can be entirely fine (its own package present, model files
        # downloaded) while numpy/soundfile -- needed here regardless of engine --
        # are the piece the installer didn't provision. See _runtime_import_die().
        _runtime_import_die(e)
    import subprocess

    ffmpeg_path = resolve_ffmpeg()
    engine = make_engine(engine_id, voices)
    sr = engine.sample_rate
    cache = args.cache or os.path.join(os.path.dirname(os.path.abspath(args.script)) or '.', '.tts-cache')
    voices, rotation = apply_rotation(voices, pools, args, cache)
    if rotation:
        for slot in sorted(rotation['chosen']):
            alts = len(rotation['pools'][slot])
            how = ('pinned' if slot in rotation['pinned']
                   else 'fixed' if args.no_rotate else 'rotated')
            print(f'  {slot}: {voices[slot]} ({how}, {alts} in pool)')
    os.makedirs(cache, exist_ok=True)
    cleanup_orphan_tmp_files(cache)

    def trim(audio):
        """Trim leading/trailing silence (< TRIM_THRESHOLD_DB)."""
        idx = np.where(np.abs(audio) > 10 ** (TRIM_THRESHOLD_DB / 20))[0]
        if not len(idx):
            return audio
        pre, post = int(TRIM_PAD[0] * sr), int(TRIM_PAD[1] * sr)
        return audio[max(0, idx[0] - pre): min(len(audio), idx[-1] + post)]

    def read_cached(path):
        """None if the file is unreadable or at the wrong sample rate -- callers
        treat that as "not cached" and delete + re-render. A valid zero-length WAV
        (a line whose spoken text produced no audio at all) is NOT corrupt -- it's
        the correct cached result for that text, and rejecting it would re-render
        that line on every single run."""
        try:
            data, file_sr = sf.read(path, dtype='float32')
        except Exception:
            return None
        if file_sr != sr:
            return None
        return data

    def write_cache_atomic(path, audio):
        # format='WAV' is explicit because the tmp name doesn't end in .wav
        # (soundfile infers format from the extension otherwise, and would refuse it).
        atomic_write(path, lambda tmp: sf.write(tmp, audio, sr, format='WAV'))

    def say(speaker, spoken_text):
        voice = voices[speaker]
        speed = speeds.get(speaker, args.speed)
        key = cache_key(engine.name, voice, sr, speed, spoken_text)
        path = os.path.join(cache, f'{key}.wav')
        if os.path.exists(path):
            cached = read_cached(path)
            if cached is not None:
                return cached
            try:
                os.remove(path)
            except OSError:
                pass
        audio, engine_sr = engine.synth(spoken_text, voice, speed)
        if engine_sr != sr:
            die(f'{engine.name}: synth() returned {engine_sr} Hz, expected {sr} Hz', 2)
        audio = trim(np.asarray(audio, dtype=np.float32)) if len(audio) else np.zeros(0, dtype=np.float32)
        write_cache_atomic(path, audio)
        return audio

    parts, said = [], 0
    chapter_records = []
    chapter_ptr = 0
    t = 0.0
    for i, ev in enumerate(events):
        while chapter_ptr < len(chapters) and chapters[chapter_ptr][1] == i:
            chapter_records.append({'title': chapters[chapter_ptr][0], 'start': t})
            chapter_ptr += 1
        if ev[0] == 'pause':
            parts.append(np.zeros(int(ev[1] * sr), dtype=np.float32))
            t += ev[1]
            continue
        audio = say(ev[1], ev[3])
        parts.append(audio)
        t += len(audio) / sr
        said += 1
        nxt = events[i + 1] if i + 1 < len(events) else None
        if nxt and nxt[0] == 'say':
            parts.append(np.zeros(int(TURN_GAP * sr), dtype=np.float32))
            t += TURN_GAP
        print(f'\r  {said} lines', end='', flush=True)

    while chapter_ptr < len(chapters):
        chapter_records.append({'title': chapters[chapter_ptr][0], 'start': t})
        chapter_ptr += 1

    audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    wav = os.path.splitext(args.out)[0] + '.wav'
    sf.write(wav, audio, sr)
    duration = len(audio) / sr

    # Tags + chapters go INTO the mp3. Without them a podcast app shows an untitled
    # file with no way to skip between segments, however good the audio is.
    tags = {
        'title': args.title or title_from_out(args.out),
        'album': args.album or 'Podcast',
        'artist': args.artist or ', '.join(dict.fromkeys(
            ev[1] for ev in events if ev[0] == 'say')).title(),
        'date': args.date or time.strftime('%Y-%m-%d'),
        'genre': 'Podcast',
        'comment': f'Generated locally with the podcast skill ({engine.name}).',
    }
    encode_mp3(wav, args.out, tags, chapter_records, duration,
               cover=args.cover, ffmpeg_path=ffmpeg_path)
    os.remove(wav)

    chapters_path = os.path.splitext(args.out)[0] + '.chapters.json'
    with open(chapters_path, 'w', encoding='utf-8') as f:
        json.dump({'duration': duration, 'chapters': chapter_records}, f, indent=2)
    print()
    for c in chapter_records:
        print(f'{fmt_mmss(c["start"])}  {c["title"]}')
    paced = {sp: sd for sp, sd in speeds.items() if abs(sd - 1.0) > 1e-9}
    cast_note = f', cast {os.path.basename(args.cast)}' if args.cast else ''
    pace_note = ('  pace: ' + ', '.join(f'{sp} {sd:g}x' for sp, sd in sorted(paced.items()))) if paced else ''
    print(f'✓ {args.out}  {duration / 60:.1f} min, {said} lines, '
          f'{len(chapter_records)} chapters  ({engine.name}, {sr} Hz{cast_note}){pace_note}')


if __name__ == '__main__':
    main()
