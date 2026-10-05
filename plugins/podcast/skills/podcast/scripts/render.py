#!/usr/bin/env python3
"""
render.py: turn a two-host podcast script into one MP3 with a local TTS engine.

Script format (plain text):
  MAYA: A line of dialogue.          speaker lines; SPEAKER must be in --voices
  ALEX: Wait. [pause 0.8] So then?   inline pause: the line is synthesised in chunks
                                      with N s of silence between them (0 < N <= 10)
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
               then a pacecheck block (pacing metrics + warnings)
  --strict     with --dry-run: exit 4 if pacecheck warns
  --pacing P   brisk | relaxed | spacious (default: config default_pacing, "relaxed").
               brisk is 0.2.0's timing, sample for sample: each line synthesised whole,
               0.32 s between lines, 1.1 s at `---`. relaxed and spacious synthesise
               each sentence on its own (cached like any chunk) with a short gap between
               sentences of one speaker and a longer one when the speaker changes; see GAPS.
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

# Silences, in seconds, by pacing and kind. The kinds name what came before the gap:
#   sentence  between two sentences of one say line (relaxed/spacious split lines into sentences)
#   continue  between two lines by the same speaker
#   handoff / question / reaction / dense   the speaker changes (most specific kind wins:
#             the line just said ends in "?", carries >= 2 figures, or is <= 5 words)
#   segment   a `---` divider
# A whole-line `[pause N]` replaces the gap (no gap is added next to it) and an inline
# `[pause N]` is exactly N. brisk is 0.2.0 (one 0.32 s gap everywhere, no sentence split) and
# must stay audio-identical to it. relaxed reproduces the owner-approved ear test (v6):
# 0.32 s within a speaker, 0.7 s at a speaker change. spacious is relaxed x 1.3 at a speaker
# change. Several kinds may share a value; the kinds exist so the values can be tuned apart.
# Gaps are not in the TTS cache key, so changing these never re-synthesises anything.
GAPS = {
    'brisk':    {'continue': 0.32, 'sentence': 0.32, 'handoff': 0.32, 'reaction': 0.32,
                 'question': 0.32, 'dense': 0.32, 'segment': 1.1},
    'relaxed':  {'continue': 0.32, 'sentence': 0.32, 'handoff': 0.7, 'reaction': 0.7,
                 'question': 0.7, 'dense': 0.7, 'segment': 2.0},
    'spacious': {'continue': 0.45, 'sentence': 0.45, 'handoff': 0.91, 'reaction': 0.91,
                 'question': 0.91, 'dense': 0.91, 'segment': 2.6},
}
PACINGS = tuple(GAPS)
GAP_KINDS = ('continue', 'sentence', 'handoff', 'reaction', 'question', 'dense', 'segment')
# 0.2.0's two constants, kept as names for brisk.
TURN_GAP, SEGMENT_GAP = GAPS['brisk']['continue'], GAPS['brisk']['segment']
# Speech-time model, fitted to measured renders (ffprobe) of two-host kokoro audio: speech =
# words / WPM * 60 + CHUNK_OVERHEAD per synthesised chunk (a chunk = the text between gaps: one
# line in brisk, one sentence in relaxed/spacious). Gaps are NOT in it; they are added from GAPS.
# Fit (least squares, 14 renders: 4 scripts of 375-1710 words x brisk/relaxed/spacious, plus two
# short ones): ~159 wpm and -0.40 s per chunk, since a chunk's leading and trailing silence is
# trimmed, so short chunks run quicker than a flat rate says. Rounded to the pair that keeps the
# worst relaxed error lowest: 163 wpm, -0.35 s -> relaxed within 3.7%, brisk within 5.4%. One flat
# rate cannot do it: full-length scripts measure ~175 wpm net of gaps and short-sentence rescripts
# ~197, and the chunk term is what reconciles them. (The old flat 158 came from a brisk render by
# an older private renderer; on today's engine it over-estimated by 7-21%.) Re-fit if GAPS, the
# trim constants or the voice engine change materially.
WPM = 163
CHUNK_OVERHEAD = -0.35
MIN_CHUNK_SECONDS = 0.3   # floor so a one-word chunk ("Huh.") never estimates to ~0

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


def parse_script(path, voices, pattern, rules, pacing='brisk'):
    """Returns (events, chapters) where events is a list of
    ('say', speaker, written_text, spoken_text[, segments]) | ('pause', seconds)
    and chapters is a list of (title, event_index) — event_index is the index in
    `events` of the next say/pause after the header, i.e. where the chapter starts.
    Under a pacing that splits sentences (not brisk), a say line of two or more
    sentences carries segments with a ('gap', 'sentence') between them (split_turn()).
    Bad input (missing file, unknown speaker, malformed pause) exits 2 naming the line."""
    events = []
    chapters = []
    split = splits_sentences(pacing)
    try:
        with open(path, encoding='utf-8') as f:
            raw_lines = f.readlines()
    except OSError as e:
        die(f'{path}: cannot read script: {e.strerror or e}', 2)
    for n, raw in enumerate(raw_lines, 1):
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
            events.append(('pause', SegmentBreak(SEGMENT_GAP)))
            continue
        if m := re.fullmatch(r'\[pause ([\d.]+)\]', line, re.ASCII):
            try:
                secs = float(m.group(1))
            except ValueError:
                die(f'{path}:{n}: invalid pause duration: {line[:60]}', 2)
            events.append(('pause', secs))
            continue
        m = re.fullmatch(r'([A-Z]+):\s*(.+)', line)
        if not m or m.group(1) not in voices:
            die(f'{path}:{n}: not a known speaker line: {line[:60]}', 2)
        written = m.group(2)
        segments = split_inline_pauses(path, n, written)  # also validates every token
        # Never cut inside a lexicon match, so a rule spanning ". " still applies whole.
        protect = [mm.span() for mm in pattern.finditer(written)] if pattern else []
        pieces = split_turn(written, protect) if split else [written]
        if len(pieces) > 1:
            # One chunk per sentence, a sentence gap between them; an inline pause inside
            # a sentence splits it further, exactly as on a one-sentence line.
            segs = []
            for j, piece in enumerate(pieces):
                if j:
                    segs.append(('gap', 'sentence'))
                inner = split_inline_pauses(path, n, piece)
                if inner is None:
                    segs.append(('text', apply_lexicon(piece, pattern, rules)))
                else:
                    segs.extend((kind, apply_lexicon(val, pattern, rules) if kind == 'text' else val)
                                for kind, val in inner)
            segs = tuple(segs)
            spoken = ' '.join(val for kind, val in segs if kind == 'text')
            events.append(('say', m.group(1), written, spoken, segs))
            continue
        if segments is None:
            spoken = apply_lexicon(written, pattern, rules)
            events.append(('say', m.group(1), written, spoken))
            continue
        # Inline pause: a 5th element carries the line as spoken chunks and silences,
        # the lexicon applied per chunk. A line without one stays a 4-tuple, so it is
        # rendered exactly as before.
        segments = tuple((kind, apply_lexicon(val, pattern, rules) if kind == 'text' else val)
                         for kind, val in segments)
        spoken = ' '.join(val for kind, val in segments if kind == 'text')
        events.append(('say', m.group(1), written, spoken, segments))
    return events, chapters


def split_inline_pauses(path, n, written):
    """None when the line has no inline pause token; else the line's segments,
    [('text', chunk) | ('pause', seconds), ...]. The syntax lives in config.py so
    qa.py strips exactly what this renders. A malformed token exits 2 naming the line.
    Without config.py (a bare checkout) there is no inline-pause syntax: the line is
    rendered as before."""
    if config is None or not config.PAUSE_TOKEN_RE.search(written):
        return None
    try:
        return config.split_inline_pauses(written)
    except ValueError as e:
        die(f'{path}:{n}: {e}: {written[:60]}', 2)


def splits_sentences(pacing):
    """Whether a pacing synthesises each sentence of a line on its own. brisk never does:
    it must reproduce 0.2.0, which synthesised whole lines."""
    return pacing != 'brisk'


def split_turn(written, protect=()):
    """A say line's written text -> its sentences, as rendered under relaxed/spacious.
    Cuts only where sentence_breaks() finds a sentence end, never inside a `protect` span
    (the lexicon's matches, so a rule like "U.S. Navy" is applied whole). A one-word
    sentence ("Okay.", "Wait.", "Honestly?") is joined to the one after it, since a lone
    word fails QA as DROPPED; "No." is the exception, an answer that stands on its own.
    A one-word LAST sentence is joined to the one before it ("It works. Okay.").
    Pieces are slices of `written`, so their text is exactly what was written."""
    cuts = [(e, b) for e, b in sentence_breaks(written)
            if not any(a < b and e < z for a, z in protect)]
    pieces, prev = [], 0
    for e, b in cuts:
        pieces.append((prev, e, b))  # (start, end of sentence, start of the next)
        prev = b
    bounds = [(start, e) for start, e, _ in pieces] + [(prev, len(written))]
    merged = []  # [start, end] slices
    for a, z in bounds:
        if merged:
            last = written[merged[-1][0]:merged[-1][1]]
            if len(last.split()) == 1 and last != 'No.':
                merged[-1][1] = z
                continue
        merged.append([a, z])
    if len(merged) > 1 and len(written[merged[-1][0]:merged[-1][1]].split()) == 1:
        tail = merged.pop()
        merged[-1][1] = tail[1]
    return [written[a:z] for a, z in merged]


def line_segments(ev):
    """A say event's segments, [('text', spoken) | ('pause', seconds) | ('gap', kind), ...].
    The one reader of the optional 5th element: a line without an inline pause or a
    sentence split is one chunk. A 'gap' is a GAPS kind, resolved per pacing."""
    return ev[4] if len(ev) > 4 else (('text', ev[3]),)


def gap_kind(prev, nxt):
    """The GAPS kind of the silence after say event `prev` when say event `nxt` follows.
    Same speaker: 'continue'. A speaker change: the most specific of 'question' (prev's last
    sentence is a question), 'dense' (>= 2 figures), 'reaction' (<= 5 words), else 'handoff'."""
    if nxt[1] == prev[1]:
        return 'continue'
    text = prev[3]
    last = (split_sentences(text) or [text])[-1]
    if re.search(r'\?["\'\u201d\u2019)\]]*$', last.rstrip()):
        return 'question'
    if len(FIGURE_RE.findall(text)) >= 2:
        return 'dense'
    if len(text.split()) <= 5:
        return 'reaction'
    return 'handoff'


def gap_for(prev, nxt, pacing):
    """Seconds of silence after say event `prev` when say event `nxt` follows."""
    return GAPS[pacing][gap_kind(prev, nxt)]


def _timeline(events, duration_of, pacing, on_line=None):
    """(ops, starts): ops as plan_assembly() returns them, and starts[i] the time event i
    begins (starts[len(events)] is the end). The one place gaps are applied."""
    g = GAPS[pacing]
    ops, starts, t = [], [], 0.0
    for i, ev in enumerate(events):
        starts.append(t)
        if ev[0] == 'pause':
            secs = g['segment'] if isinstance(ev[1], SegmentBreak) else ev[1]
            ops.append(('silence', secs))
            t += secs
            continue
        for kind, val in line_segments(ev):
            if kind == 'text':
                ops.append(('say', ev[1], val))
                t += duration_of(ev[1], val)
            else:
                secs = val if kind == 'pause' else g[val]
                ops.append(('silence', secs))
                t += secs
        if on_line:
            on_line()
        nxt = events[i + 1] if i + 1 < len(events) else None
        if nxt and nxt[0] == 'say':
            secs = gap_for(ev, nxt, pacing)
            ops.append(('silence', secs))
            t += secs
    starts.append(t)
    return ops, starts


def plan_assembly(events, chapters, duration_of, on_line=None, pacing='brisk'):
    """The render's timeline, engine-free. Returns (ops, chapter_records): ops are
    ('say', speaker, spoken_text) | ('silence', seconds) in playback order, and each
    chapter record is {'title', 'start'}. duration_of(speaker, text) gives a chunk's
    length in seconds (main() synthesises it there); on_line() fires after each line.
    Gaps come from GAPS[pacing]; the events must be parsed under the same pacing."""
    ops, starts = _timeline(events, duration_of, pacing, on_line)
    records = [{'title': title, 'start': starts[min(idx, len(events))]} for title, idx in chapters]
    return ops, records


class Episode:
    """A script parsed under one pacing: the one path from text to timeline that --dry-run
    (estimate, pacecheck) and the render (plan) both take, so the pacing is applied the
    same way everywhere and cannot be dropped at a call site."""

    def __init__(self, path, voices, pattern, rules, pacing):
        self.pacing = pacing
        self.events, self.chapters = parse_script(path, voices, pattern, rules, pacing)

    def estimate(self):
        return estimate_seconds(self.events, self.pacing)

    def pacecheck(self):
        return pacecheck(self.events, self.chapters, pacing=self.pacing)

    def plan(self, duration_of, on_line=None):
        return plan_assembly(self.events, self.chapters, duration_of, on_line, pacing=self.pacing)


def estimate_seconds(events, pacing='brisk'):
    """Returns (total_seconds, chapter_start_seconds_by_event_index): plan_assembly()'s
    timeline with speech timed at WPM, so the estimate and the render share every gap."""
    _ops, starts = _timeline(events, lambda _speaker, text: speech_seconds(text), pacing)
    return starts[-1], dict(enumerate(starts))


# ---------------------------------------------------------------------------
# pacecheck: a deterministic, offline pacing report printed by --dry-run.
# Targets come from the PRD (Goals > Quantitative Metrics). The warning kinds and the
# printed line prefixes ("pacecheck  ", "  pauses ", "  seg ", "  ⚠ KIND: ") are a
# contract read by the model, CI and the eval runner; the thresholds are tunable.
# ---------------------------------------------------------------------------
PACE_KINDS = ('NO_PAUSE', 'LONG_RUN', 'FLAT_LINES', 'TELLER_CHANGED', 'NONLEXICAL_ALONE', 'NONLEXICAL_MANY',
              'BANNED_SOUND')
PAUSE_EVERY_SECS = 90.0       # at least one pause per this many seconds of script
MAX_PAUSE_FREE_SECS = 180.0   # no stretch inside a segment longer than this without a pause
LONG_RUN_WORDS = 90           # longest single-speaker run (skipped for a one-voice script)
SHORT_SENTENCE_WORDS = 6      # a "short" sentence, for the FLAT_LINES share
# Share of SENTENCES (not lines) of <= SHORT_SENTENCE_WORDS words that counts as varied.
# The orchestrator sets this band; see the 2.1 report for the measured scripts.
FLAT_LINES_BAND = (0.40, 0.70)
FLAT_LINES_MIN_SENTENCES = 20  # below this many sentences (per segment / episode) the share isn't judged
LISTENER_LINE_WORDS = 5       # role heuristic: a turn this short counts toward "listener"
NONLEXICAL_PER_SEGMENT = 1    # allowlisted sounds per segment
STRICT_EXIT = 4               # --dry-run --strict with any warning (3 means "not installed")

FIGURE_RE = re.compile(r'\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|million|'
                       r'billion|percent|\d[\d,.]*)\b', re.I)
# A sentence ends at . ! or ? (and any closing quote or bracket) followed by a space or the
# end, but not at a "..." hold. sentence_breaks() adds the cases that are not an end.
SENTENCE_END_RE = re.compile(r'(?:[!?]+|(?<!\.)\.(?!\.))["\'\u201d\u2019)\]]*(?:\s+|$)')
# Titles that are followed by a name, so their full stop never ends a sentence.
TITLE_ABBREVS = frozenset({'Mr.', 'Mrs.', 'Ms.', 'Dr.', 'St.', 'Mt.', 'Prof.', 'vs.'})
DOTTED_ABBREV_RE = re.compile(r'(?:[A-Za-z]\.){2,}')  # U.S., p.m., e.g., i.e.


class SegmentBreak(float):
    """The silence a `---` divider adds. It equals SEGMENT_GAP (brisk), so events compare
    as before; the timeline uses GAPS[pacing]['segment'] for it, and pacecheck tells it
    apart from a written `[pause N]`."""
    __slots__ = ()


def speech_seconds(text):
    """Estimated speech time of ONE synthesised chunk of spoken text (no gaps): words at WPM
    plus CHUNK_OVERHEAD, floored at MIN_CHUNK_SECONDS."""
    return max(MIN_CHUNK_SECONDS, len(text.split()) / WPM * 60.0 + CHUNK_OVERHEAD)


def sentence_breaks(text):
    """[(end, next_start)] for each sentence end inside `text`: the one definition of a
    sentence boundary, shared by the renderer (split_turn) and pacecheck (split_sentences).
    Not a boundary: a "..." hold; the end of the text; a full stop after a title (Mr., Dr.)
    or a dotted abbreviation (U.S., p.m., e.g.); a stop followed by a lowercase letter or a
    digit ("item No. 5"); one inside an open double quote; one followed by an inline
    [pause N] (a beat stays with the sentence it follows)."""
    out = []
    for m in SENTENCE_END_RE.finditer(text):
        nxt = m.end()
        end = len(text[:nxt].rstrip())
        if nxt >= len(text) or end <= 0:
            continue
        c = text[nxt]
        if c.islower() or c.isdigit() or text[nxt:nxt + 6].lower() == '[pause':
            continue
        word = text[:end].split()[-1].rstrip('"\'\u201d\u2019)]')
        if word in TITLE_ABBREVS or DOTTED_ABBREV_RE.fullmatch(word):
            continue
        head = text[:end]
        if head.count('"') % 2 or head.count('\u201c') > head.count('\u201d'):
            continue
        out.append((end, nxt))
    return out


def split_sentences(text):
    """Spoken text -> sentences (each with at least one word), cut at sentence_breaks()."""
    out, pos = [], 0
    for end, nxt in sentence_breaks(text):
        out.append(text[pos:end].strip())
        pos = nxt
    out.append(text[pos:].strip())
    return [s for s in out if re.search(r'\w', s)]


def _pace_timeline(events, chapters, pacing='brisk'):
    """[(event_idx, kind, seconds)] with kind speech|pause|break|gap, read from
    plan_assembly() so turn gaps are whatever the render uses. A `[pause N]` line and
    an inline pause are 'pause'; a `---` divider is 'break'; a sentence or turn gap is
    'gap'; '...' is just speech."""
    ops, _ = plan_assembly(events, chapters, lambda _speaker, text: speech_seconds(text), pacing=pacing)
    out, k = [], 0
    for i, ev in enumerate(events):
        if ev[0] == 'pause':
            kinds = ['break' if isinstance(ev[1], SegmentBreak) else 'pause']
        else:
            kinds = [{'text': 'speech', 'pause': 'pause', 'gap': 'gap'}[kind] for kind, _ in line_segments(ev)]
            nxt = events[i + 1] if i + 1 < len(events) else None
            if nxt and nxt[0] == 'say':
                kinds.append('gap')
        for kind in kinds:
            op = ops[k] if k < len(ops) else None
            if op is None or (op[0] == 'say') != (kind == 'speech'):
                raise RuntimeError('pacecheck: plan_assembly() ops no longer line up with events')
            out.append((i, kind, speech_seconds(op[2]) if kind == 'speech' else op[1]))
            k += 1
    if k != len(ops):
        raise RuntimeError('pacecheck: plan_assembly() ops no longer line up with events')
    return out


def _pace_segments(events, chapters):
    """Segments split at chapter headers and `---` dividers; ones without a line are dropped."""
    titles = {}
    for title, idx in chapters:
        titles.setdefault(idx, title)
    cuts = {0, *titles}
    cuts.update(i + 1 for i, ev in enumerate(events) if ev[0] == 'pause' and isinstance(ev[1], SegmentBreak))
    bounds = sorted(c for c in cuts if c < len(events)) + [len(events)]
    return [{'title': titles.get(a), 'start': a, 'end': b} for a, b in zip(bounds, bounds[1:])
            if any(events[j][0] == 'say' for j in range(a, b))]


# Every m-spelling of "mm-hm" ("Mm-hm", "Mhm", "Mmhmm", "Mm") is spelled out as letters by
# Kokoro (ledger L14), so pacecheck flags it rather than counting it as a sound.
BANNED_SOUND_RE = re.compile(r"(?<![\w'-])(m+-?h+m+|m{2,})(?![\w'-])", re.I)


def find_sounds(text, nonlexical):
    """-> (sounds found, as their NONLEXICAL keys; text with them blanked out). Longest key
    first, so "uh-huh" is not also a "huh"; a repeat ("ha-ha", "ha ha") is one sound."""
    found = []
    for key in sorted(nonlexical, key=len, reverse=True):
        k = re.escape(key)
        rx = re.compile(r"(?<![\w'-])" + k + r"(?:[- ]" + k + r")*(?![\w'-])", re.I)
        found += [key] * len(rx.findall(text))
        text = rx.sub(' ', text)
    return found, text


def _written_words(ev):
    """A say line as written, inline pause tokens removed (config.py owns that syntax)."""
    return config.strip_inline_pauses(ev[2]) if config is not None else ev[2]


def _spoken_text(ev):
    return ' '.join(val for kind, val in line_segments(ev) if kind == 'text')


def _flat_lines(sentence_words):
    """FLAT_LINES message for a list of sentence lengths, or None (in band, or too few to judge)."""
    if len(sentence_words) < FLAT_LINES_MIN_SENTENCES:
        return None
    share = sum(1 for w in sentence_words if w <= SHORT_SENTENCE_WORDS) / len(sentence_words)
    lo, hi = FLAT_LINES_BAND
    if lo <= share <= hi:
        return None
    return (f'{share:.0%} of {len(sentence_words)} sentences are {SHORT_SENTENCE_WORDS} words or fewer '
            f'(aim for {lo:.0%}-{hi:.0%})')


def pacecheck(events, chapters, nonlexical=None, pacing='brisk'):
    """Pacing metrics and warnings for parsed events (parse_script(), same pacing). Pure: no I/O.
    -> {'lines', 'short_share', 'sentences', 'avg_words', 'sd_words', 'pauses',
        'secs_per_pause', 'longest_pause_free': (secs, seg_no), 'longest_run':
        (speaker, words, event_idx), 'nonlexical': n, 'sounds': {sound: n},
        'figures_per_min', 'segments': [...], 'warnings': [(kind, msg)]}
    short_share is the share of SENTENCES of <= SHORT_SENTENCE_WORDS words."""
    import statistics
    if nonlexical is None:
        nonlexical = config.NONLEXICAL if config is not None else {}
    total, _starts = estimate_seconds(events, pacing)
    timeline = _pace_timeline(events, chapters, pacing)
    says = [(i, ev) for i, ev in enumerate(events) if ev[0] == 'say']
    line_no = {i: n for n, (i, _) in enumerate(says, 1)}
    words = [len(_spoken_text(ev).split()) for _, ev in says]
    sentences = [len(s.split()) for _, ev in says for s in split_sentences(_spoken_text(ev))]
    speakers = {ev[1] for _, ev in says}
    pauses = sum(1 for _, kind, _ in timeline if kind == 'pause')
    warnings, segs, sounds = [], [], {}
    longest_run, longest_free = (None, 0, None), (0.0, None)
    total_figures = 0

    for n, seg in enumerate(_pace_segments(events, chapters), 1):
        a, b = seg['start'], seg['end']
        label = f'segment {n}' + (f' "{seg["title"]}"' if seg['title'] else '')
        items = [t for t in timeline if a <= t[0] < b]
        secs = sum(t[2] for t in items)
        free = best_free = 0.0
        for _, kind, dur in items:
            if kind == 'pause':
                free = 0.0
            elif kind != 'break':  # a closing `---` divider is the segment's end, not speech
                free += dur
                best_free = max(best_free, free)
        seg_pauses = sum(1 for t in items if t[1] == 'pause')
        lines = [(i, events[i]) for i in range(a, b) if events[i][0] == 'say']
        figures = sum(len(FIGURE_RE.findall(_spoken_text(ev))) for _, ev in lines)
        total_figures += figures
        # Runs: consecutive lines by one speaker (pauses don't end a run; a segment does).
        run = (None, 0, None)
        for i, ev in lines:
            w = len(_spoken_text(ev).split())
            run = (ev[1], run[1] + w, run[2]) if ev[1] == run[0] else (ev[1], w, i)
            if run[1] > longest_run[1]:
                longest_run = run
        # Sounds: counted per segment; a line that is only sound(s) is ALONE.
        seg_sounds = 0
        for i, ev in lines:
            text = _written_words(ev)
            found, rest = find_sounds(text, nonlexical)
            for s in found:
                sounds[s] = sounds.get(s, 0) + 1
            seg_sounds += len(found)
            banned = BANNED_SOUND_RE.findall(text)
            if banned:
                warnings.append(('BANNED_SOUND', f'dialogue line {line_no[i]} ({ev[1]}: {ev[2][:40]!r}) says '
                                 f'{banned[0]!r}; Kokoro spells it as letters, use words ("Right.", "Okay.")'))
            if found and not re.search(r'\w', rest):
                warnings.append(('NONLEXICAL_ALONE', f'dialogue line {line_no[i]} ({ev[1]}: {ev[2][:40]!r}) '
                                 f'is a sound on its own; put it in front of words'))
        if seg_sounds > NONLEXICAL_PER_SEGMENT:
            warnings.append(('NONLEXICAL_MANY', f'{label}: {seg_sounds} non-lexical sounds '
                             f'(at most {NONLEXICAL_PER_SEGMENT} per segment)'))
        # Roles: the listener (learner) asks the questions and takes the short turns. Scored
        # per TURN (consecutive lines by one speaker), so one-sentence-per-line writing
        # doesn't make the explainer look like the listener.
        turns = []
        for _, ev in lines:
            if turns and turns[-1][0] == ev[1]:
                turns[-1][1].append(_spoken_text(ev))
            else:
                turns.append((ev[1], [_spoken_text(ev)]))
        score = {}
        for speaker, texts in turns:
            text = ' '.join(texts)
            score[speaker] = score.get(speaker, 0) + ('?' in text) + (len(text.split()) <= LISTENER_LINE_WORDS)
        teller = listener = None
        if len(score) >= 2:
            ranked = sorted(score.values())
            if ranked[0] < ranked[1]:
                teller = min(score, key=score.get)
            if ranked[-1] > ranked[-2]:
                listener = max(score, key=score.get)
        if best_free > MAX_PAUSE_FREE_SECS:
            warnings.append(('NO_PAUSE', f'{label}: no pause in {best_free / 60:.1f} min '
                             f'(at most {MAX_PAUSE_FREE_SECS / 60:g} min)'))
        elif secs > PAUSE_EVERY_SECS and (not seg_pauses or secs / seg_pauses > PAUSE_EVERY_SECS):
            rate = f'1 per {secs / seg_pauses:.0f} s' if seg_pauses else 'none'
            warnings.append(('NO_PAUSE', f'{label}: pauses {rate} over {secs / 60:.1f} min '
                             f'(at least 1 per {PAUSE_EVERY_SECS:.0f} s)'))
        seg_sentences = [len(x.split()) for _, ev in lines for x in split_sentences(_spoken_text(ev))]
        flat = _flat_lines(seg_sentences)
        if flat:
            warnings.append(('FLAT_LINES', f'{label}: {flat}'))
        if best_free > longest_free[0]:
            longest_free = (best_free, n)
        segs.append({'n': n, 'title': seg['title'], 'secs': secs, 'pauses': seg_pauses,
                     'longest_pause_free': best_free, 'lines': len(lines),
                     'figures_per_min': figures / (secs / 60.0) if secs else 0.0,
                     'nonlexical': seg_sounds, 'teller': teller, 'listener': listener,
                     'role_score': score, 'label': label, 'sentences': len(seg_sentences)})

    secs_per_pause = total / pauses if pauses else None
    if (len(segs) > 1 and total > PAUSE_EVERY_SECS  # one segment: already judged above
            and (secs_per_pause is None or secs_per_pause > PAUSE_EVERY_SECS)):
        rate = f'1 per {secs_per_pause:.0f} s' if pauses else 'none'
        warnings.append(('NO_PAUSE', f'pauses {rate} over {total / 60:.1f} min '
                         f'(at least 1 per {PAUSE_EVERY_SECS:.0f} s)'))
    if len(speakers) >= 2 and longest_run[1] > LONG_RUN_WORDS:
        warnings.append(('LONG_RUN', f'{longest_run[0]} speaks {longest_run[1]} words in a row from dialogue '
                         f'line {line_no[longest_run[2]]} (at most {LONG_RUN_WORDS})'))
    short_share = sum(1 for w in sentences if w <= SHORT_SENTENCE_WORDS) / len(sentences) if sentences else 0.0
    flat = _flat_lines(sentences) if len(segs) > 1 else None  # one segment: already judged above
    if flat:
        warnings.append(('FLAT_LINES', f'episode: {flat}'))
    # Fixed roles are a two-voice rule (casts/two-host.md `## Roles`): one host teaches every body segment. On a
    # panel the guests take turns telling by design (casts/panel.md), and a solo narrator always tells. The cold
    # open and the wrap (first and last segment, once there are at least three) and "roles unclear" segments are
    # not judged. The episode's teller is the one who tells most body segments; a tie goes to the earliest.
    body = segs[1:-1] if len(segs) >= 3 else segs
    clear = [s for s in body if s['teller']] if len(speakers) == 2 else []
    if clear:
        counts = {}
        for s in clear:
            counts[s['teller']] = counts.get(s['teller'], 0) + 1
        top = max(counts.values())
        episode_teller = next(s['teller'] for s in clear if counts[s['teller']] == top)
        for s in clear:
            if s['teller'] != episode_teller:
                warnings.append(('TELLER_CHANGED', f'{s["label"]}: {s["teller"]} tells, but {episode_teller} '
                                 f'tells {top} of {len(clear)} body segments; keep one teller all episode'))
    # Warnings in a stable order: by kind, then as found.
    warnings.sort(key=lambda w: PACE_KINDS.index(w[0]))
    return {'lines': len(says), 'short_share': short_share, 'sentences': len(sentences),
            'avg_words': statistics.mean(words) if words else 0.0,
            'sd_words': statistics.pstdev(words) if words else 0.0,
            'pauses': pauses, 'secs_per_pause': secs_per_pause, 'total_secs': total,
            'longest_pause_free': longest_free, 'longest_run': longest_run,
            'nonlexical': sum(sounds.values()), 'sounds': sounds,
            'figures_per_min': total_figures / (total / 60.0) if total else 0.0,
            'segments': segs, 'warnings': warnings}


def print_pacecheck(pc):
    print(f"pacecheck  sentences ≤{SHORT_SENTENCE_WORDS} words {pc['short_share']:.0%} of {pc['sentences']}"
          f"   line avg {pc['avg_words']:.1f} words (sd {pc['sd_words']:.1f}) over {pc['lines']} lines")
    rate = f"1 per {pc['secs_per_pause']:.0f} s" if pc['pauses'] else 'none'
    free, free_seg = pc['longest_pause_free']
    run = pc['longest_run']
    sounds = ', '.join(f'{k} {v}' for k, v in sorted(pc['sounds'].items())) or 'none'
    print(f"  pauses {pc['pauses']} ({rate})   longest pause-free {fmt_mmss(free)}"
          + (f' (seg {free_seg})' if free_seg else '')
          + (f"   longest run {run[0]} {run[1]} words" if run[0] else '')
          + f"   sounds {pc['nonlexical']} ({sounds})   figures {pc['figures_per_min']:.1f}/min")
    for s in pc['segments']:
        roles = f"{s['teller']}→{s['listener']}" if s['teller'] and s['listener'] else 'unclear'
        title = f' "{s["title"]}"' if s['title'] else ''
        print(f"  seg {s['n']}{title}  {fmt_mmss(s['secs'])}  pauses {s['pauses']}  "
              f"pause-free {fmt_mmss(s['longest_pause_free'])}  roles {roles}  sounds {s['nonlexical']}")
    for kind, msg in pc['warnings']:
        print(f"  ⚠ {kind}: {msg}")


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
    ap.add_argument('--pacing', choices=PACINGS, default=None,
                    help='silences between sentences, turns and segments: brisk (0.2.0 timing), '
                         'relaxed or spacious (default: config default_pacing, "relaxed")')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--strict', action='store_true',
                    help='with --dry-run: exit 4 if pacecheck prints any warning')
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


def _ref_speech(*chunk_words):
    """Selftest reference for the speech model, written out independently of speech_seconds():
    each chunk of n words is n / WPM minutes plus CHUNK_OVERHEAD, never below MIN_CHUNK_SECONDS."""
    return sum(max(MIN_CHUNK_SECONDS, n / WPM * 60.0 + CHUNK_OVERHEAD) for n in chunk_words)


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
        import io, contextlib
        err_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(err_buf):
                parse_script(bad_path, voices, pattern, rules)
            check('unknown speaker exits', False)
        except SystemExit as e:
            check('unknown speaker exits 2 (bad input), not 1', e.code == 2)
            check('unknown speaker error names line 2', err_buf.getvalue().startswith(f'{bad_path}:2:'))

        # [pause 1.2.3] is a clean error naming the line, not a crash.
        pause_path = os.path.join(td, 'badpause.txt')
        with open(pause_path, 'w', encoding='utf-8') as f:
            f.write("MAYA: hi\n[pause 1.2.3]\n")
        err_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(err_buf):
                parse_script(pause_path, voices, pattern, rules)
            check('[pause 1.2.3] exits with a clean error', False)
        except SystemExit as e:
            check('[pause 1.2.3] exits 2 (bad input), not 1', e.code == 2)
            check('bad pause error names line 2', err_buf.getvalue().startswith(f'{pause_path}:2:'))
        # A missing script is bad input too: exit 2 with a message, never a traceback.
        err_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(err_buf):
                parse_script(os.path.join(td, 'no-such-script.txt'), voices, pattern, rules)
            check('missing script exits 2', False)
        except SystemExit as e:
            check('missing script exits 2 naming the file',
                  e.code == 2 and 'no-such-script.txt' in err_buf.getvalue())
        except Exception as e:  # a traceback is the bug this guards against
            check(f'missing script exits 2 (got {type(e).__name__})', False)

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
        expected = _ref_speech(5) + 2.0 + _ref_speech(3)
        check('duration estimate matches manual arithmetic', abs(total - expected) < 1e-9)
        check('chapter start for first event is 0.0', starts[0] == 0.0)
        check('chapter start after pause accounts for speech + pause',
              abs(starts[2] - (_ref_speech(5) + 2.0)) < 1e-9)

        # Inline [pause N] inside a speaker line: the line splits into spoken chunks
        # with silence between them, the lexicon applies per chunk, and the whole thing
        # stays ONE say event (a one-word line alone fails QA as DROPPED).
        inline_path = os.path.join(td, 'inline.txt')
        with open(inline_path, 'w', encoding='utf-8') as f:
            f.write("MAYA: The X-team met today.\n"
                    "ALEX: Wait. [pause 0.8] So the X-team was wrong?\n"
                    "MAYA: Yes. [pause 0.3] [pause 0.25] Mostly.\n")
        in_events, _ = parse_script(inline_path, voices, pattern, rules)
        check('inline pause: line parses into chunks + silence (one say event)',
              len(in_events) == 3 and in_events[1] == (
                  'say', 'ALEX', 'Wait. [pause 0.8] So the X-team was wrong?',
                  'Wait. So the ex team was wrong?',
                  (('text', 'Wait.'), ('pause', 0.8), ('text', 'So the ex team was wrong?'))))
        check('inline pause: consecutive pauses stay separate segments',
              line_segments(in_events[2]) == (('text', 'Yes.'), ('pause', 0.3), ('pause', 0.25), ('text', 'Mostly.')))
        check('a line without an inline pause produces the same 4-tuple event as before',
              in_events[0] == ('say', 'MAYA', 'The X-team met today.',
                               apply_lexicon('The X-team met today.', pattern, rules)))
        # estimate_seconds() counts the inline silence, so --dry-run matches the render.
        in_total, _ = estimate_seconds(in_events)
        in_expected = _ref_speech(5, 1, 6, 1, 1) + 2 * TURN_GAP + 0.8 + 0.3 + 0.25
        check('estimate includes inline pause seconds', abs(in_total - in_expected) < 1e-9)
        for bad_tok in ('[pause 1.2.3]', '[pause 0]', '[pause 10.5]', '[Pause 1]', '[pause 0.8',
                        '[pause 1] .'):  # last: a chunk with no word is rejected, not merged
            badin_path = os.path.join(td, 'badinline.txt')
            with open(badin_path, 'w', encoding='utf-8') as f:
                f.write(f"MAYA: fine.\n\nALEX: Wait. {bad_tok}\n" if bad_tok.endswith('.')
                        else f"MAYA: fine.\n\nALEX: Wait. {bad_tok} So?\n")
            err_buf = io.StringIO()
            try:
                with contextlib.redirect_stderr(err_buf):
                    parse_script(badin_path, voices, pattern, rules)
                check(f'malformed inline {bad_tok!r} exits 2 naming line 3', False)
            except SystemExit as e:
                check(f'malformed inline {bad_tok!r} exits 2 naming line 3',
                      e.code == 2 and err_buf.getvalue().startswith(f'{badin_path}:3:'))
        # A bracket with no number is dialogue, not a directive: rendered as before.
        lit_path = os.path.join(td, 'literal.txt')
        lit_lines = ['Hit [pause] then play.', 'The [pause-button] sticks.', 'Say [pause x] aloud.']
        with open(lit_path, 'w', encoding='utf-8') as f:
            f.write(''.join(f'MAYA: {t}\n' for t in lit_lines))
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                lit_events, _ = parse_script(lit_path, voices, pattern, rules)
        except SystemExit:
            lit_events = None
        check('"[pause]", "[pause-button]", "[pause x]" in dialogue render as before (plain 4-tuples)',
              lit_events == [('say', 'MAYA', t, apply_lexicon(t, pattern, rules)) for t in lit_lines])

        # plan_assembly(): the render's timeline, with a fake duration (0.1 s per char).
        fake = lambda sp, text: len(str(text)) / 10.0
        plan_events = [('say', 'MAYA', 'Hi.', 'Hi.'),
                       ('say', 'ALEX', 'Wait. [pause 0.8] So?', 'Wait. So?',
                        (('text', 'Wait.'), ('pause', 0.8), ('text', 'So?'))),
                       ('say', 'MAYA', 'Yes.', 'Yes.')]
        ops, recs = plan_assembly(plan_events, [('One', 0), ('Two', 2)], fake)
        check('plan: silence sits between the chunks, turn gaps unchanged',
              ops == [('say', 'MAYA', 'Hi.'), ('silence', TURN_GAP),
                      ('say', 'ALEX', 'Wait.'), ('silence', 0.8), ('say', 'ALEX', 'So?'),
                      ('silence', TURN_GAP), ('say', 'MAYA', 'Yes.')])
        check('plan: a chapter after an inline line starts after its pause',
              [r['title'] for r in recs] == ['One', 'Two'] and recs[0]['start'] == 0.0
              and abs(recs[1]['start'] - (0.3 + TURN_GAP + 0.5 + 0.8 + 0.3 + TURN_GAP)) < 1e-9)
        old_events = [('say', 'MAYA', 'Hi.', 'Hi.'), ('pause', 1.5), ('pause', SEGMENT_GAP),
                      ('say', 'ALEX', 'Ok.', 'Ok.'), ('say', 'MAYA', 'Bye.', 'Bye.')]
        old_ops, old_recs = plan_assembly(old_events, [('End', 4)], fake)
        check('plan: a script without inline pauses gives exactly the old op sequence',
              old_ops == [('say', 'MAYA', 'Hi.'), ('silence', 1.5), ('silence', SEGMENT_GAP),
                          ('say', 'ALEX', 'Ok.'), ('silence', TURN_GAP), ('say', 'MAYA', 'Bye.')]
              and abs(old_recs[0]['start'] - (0.3 + 1.5 + SEGMENT_GAP + 0.3 + TURN_GAP)) < 1e-9)
        lines_seen = []
        plan_assembly(plan_events, [], fake, on_line=lambda: lines_seen.append(1))
        check('plan: on_line fires once per line, not per chunk', len(lines_seen) == 3)

        # ── 3.1 pacing ─────────────────────────────────────────────────────────
        nolex = (None, {})
        pace_path = os.path.join(td, 'pacing.txt')
        with open(pace_path, 'w', encoding='utf-8') as f:
            f.write("# ── 1. One ──\n"
                    "MAYA: Back to the start. A boat can sail upwind.\n"
                    "MAYA: Can it point straight at the wind?\n"
                    "ALEX: Okay. So it zigzags. Wait. [pause 0.6] Really?\n"
                    "[pause 1.2]\n"
                    "MAYA: No. It tacks.\n"
                    "---\n"
                    "ALEX: Got it.\n")

        def pace_ops(pacing, path=pace_path, fn=None):
            ev, ch = parse_script(path, voices, *nolex, pacing)
            return plan_assembly(ev, ch, fn or (lambda sp, text: 1.0), pacing=pacing)[0]

        # (A) brisk is 0.2.0: whole lines, 0.32 between any two lines, 1.1 at ---, a
        # [pause N] line replaces the gap. The literal numbers are 0.2.0's TURN_GAP/SEGMENT_GAP.
        check('brisk: the 0.2.0 op sequence (whole lines, 0.32 s gaps, 1.1 s segment)',
              pace_ops('brisk') == [
                  ('say', 'MAYA', 'Back to the start. A boat can sail upwind.'), ('silence', 0.32),
                  ('say', 'MAYA', 'Can it point straight at the wind?'), ('silence', 0.32),
                  ('say', 'ALEX', 'Okay. So it zigzags. Wait.'), ('silence', 0.6), ('say', 'ALEX', 'Really?'),
                  ('silence', 1.2), ('say', 'MAYA', 'No. It tacks.'), ('silence', 1.1),
                  ('say', 'ALEX', 'Got it.')])
        b_ev, _ = parse_script(pace_path, voices, *nolex, 'brisk')
        check('brisk: a line without an inline pause stays a 4-tuple (never sentence-split)',
              [len(e) for e in b_ev if e[0] == 'say'] == [4, 4, 5, 4, 4])
        check('GAPS: brisk is 0.32 everywhere and 1.1 at a segment; TURN_GAP/SEGMENT_GAP name it',
              all(v == 0.32 for k, v in GAPS['brisk'].items() if k != 'segment')
              and GAPS['brisk']['segment'] == 1.1 and (TURN_GAP, SEGMENT_GAP) == (0.32, 1.1))
        check('GAPS: every pacing has every kind (continue, sentence, handoff, reaction, question, dense, segment)',
              all(set(row) == set(GAP_KINDS) for row in GAPS.values()) and len(GAP_KINDS) == 7)
        check('GAPS: pacings are brisk, relaxed, spacious and match config.PACINGS',
              PACINGS == ('brisk', 'relaxed', 'spacious')
              and (config is None or tuple(config.PACINGS) == PACINGS))

        # (B) relaxed splits a line into sentences with the v6 formatter's rules. The oracle
        # is that formatter's own loop, copied verbatim.
        def fmt2_oracle(text):
            merged = []
            for sent in re.split(r'(?<=[^.][.?!])\s+(?!\[pause)', text):
                if merged and (len(merged[-1].split()) == 1 and merged[-1] != 'No.'):
                    merged[-1] += ' ' + sent
                else:
                    merged.append(sent)
            return merged
        split_cases = {
            'Wait. [pause 0.7] So the diagram is just wrong?': ['Wait. [pause 0.7] So the diagram is just wrong?'],
            'Which makes no sense. Wind pushes. How... do you get pushed?':
                ['Which makes no sense.', 'Wind pushes.', 'How... do you get pushed?'],
            "Okay. So tacking isn't a trick. It's just how you go upwind.":
                ["Okay. So tacking isn't a trick.", "It's just how you go upwind."],
            'No. Roughly forty-five degrees. Sailors call that the no-go zone.':
                ['No.', 'Roughly forty-five degrees.', 'Sailors call that the no-go zone.'],
            'Honestly? Knowing the wing part helps. I want that first.':
                ['Honestly? Knowing the wing part helps.', 'I want that first.'],
            'So the gentle turn is the one into the wind. Got it.':
                ['So the gentle turn is the one into the wind.', 'Got it.'],
            'I would have pictured the wind... just pushing it.': ['I would have pictured the wind... just pushing it.'],
            'Hold on. [pause 0.5] Let me try it back. The sail... pulls sideways.':
                ['Hold on. [pause 0.5] Let me try it back.', 'The sail... pulls sideways.'],
            'Right. Fine. So that works!': ['Right. Fine.', 'So that works!'],
        }
        # The formatter behind v6 and split_turn() agree on every case above; the cases
        # below are where split_turn() deliberately does better (review of 3.1).
        better_cases = {
            'It stops. Done.': ['It stops. Done.'],  # a one-word last sentence joins the one before
            'It works. Okay.': ['It works. Okay.'],
            'The U.S. Navy sailed. Then it docked.': ['The U.S. Navy sailed.', 'Then it docked.'],
            'The U.S. economy grew. Then it shrank.': ['The U.S. economy grew.', 'Then it shrank.'],
            'Use a tool, e.g. a hammer. Then stop.': ['Use a tool, e.g. a hammer.', 'Then stop.'],
            'At 5 p.m. we met. Then we left.': ['At 5 p.m. we met.', 'Then we left.'],
            'Mr. and Mrs. Smith came. Dr. Jones came too.': ['Mr. and Mrs. Smith came.', 'Dr. Jones came too.'],
            'Look at item No. 5 today. Then go.': ['Look at item No. 5 today.', 'Then go.'],
            'It grew 4. 5 percent is a lot.': ['It grew 4. 5 percent is a lot.'],
            'He said "Go. Now." Then he left.': ['He said "Go. Now."', 'Then he left.'],
            'She asked (why?) Then she left.': ['She asked (why?)', 'Then she left.'],
            'Is it...? Yes it is.': ['Is it...?', 'Yes it is.'],
            'It was... Huge, really. Then calm.': ['It was... Huge, really.', 'Then calm.'],  # a hold, not an end
        }
        check('relaxed: split_turn() gives the expected sentences ("...", inline pause, one-word merge, "No.")',
              all(split_turn(t) == want for t, want in split_cases.items()))
        bad = [t for t, want in better_cases.items() if split_turn(t) != want]
        check('relaxed: no cut inside an abbreviation (U.S., e.g., p.m., Mr./Dr., No. 5), a number or a quote; '
              'a lone last word joins the sentence before' + (f' -- wrong: {bad}' if bad else ''), not bad)
        check('pacecheck counts sentences at the same boundaries the renderer cuts',
              [len(split_sentences(t)) for t in ('The U.S. Navy sailed. Then it docked.',
                                                     'He said "Go. Now." Then he left.', 'At 5 p.m. we met.',
                                                     'Wait... no. Yes!')] == [2, 2, 1, 2])
        check('relaxed: split_turn() agrees with the v6 formatter on every fixture',
              all(split_turn(t) == fmt2_oracle(t) for t in split_cases))
        check('relaxed: a doubled space before an inline pause does not split off the beat',
              split_turn('Wait.  [pause 0.5] So?') == ['Wait.  [pause 0.5] So?'])

        # (C) relaxed gaps: 0.32 between sentences and same-speaker lines, 0.7 at a speaker
        # change, a [pause N] line replaces the gap, an inline pause is exact.
        check('relaxed: sentence chunks, 0.32 s within a speaker, 0.7 s at a handoff, 2.0 s segment',
              pace_ops('relaxed') == [
                  ('say', 'MAYA', 'Back to the start.'), ('silence', 0.32),
                  ('say', 'MAYA', 'A boat can sail upwind.'), ('silence', 0.32),
                  ('say', 'MAYA', 'Can it point straight at the wind?'), ('silence', 0.7),
                  ('say', 'ALEX', 'Okay. So it zigzags.'), ('silence', 0.32), ('say', 'ALEX', 'Wait.'),
                  ('silence', 0.6), ('say', 'ALEX', 'Really?'),
                  ('silence', 1.2), ('say', 'MAYA', 'No.'), ('silence', 0.32), ('say', 'MAYA', 'It tacks.'),
                  ('silence', 2.0), ('say', 'ALEX', 'Got it.')])
        r_ev, _ = parse_script(pace_path, voices, *nolex, 'relaxed')
        check('relaxed: a split line is still ONE say event, its spoken text unchanged',
              [e[3] for e in r_ev if e[0] == 'say'] == [e[3] for e in b_ev if e[0] == 'say'])
        say = lambda sp, text: ('say', sp, text, text)
        check('gap_kind: same speaker is continue, even after a question',
              gap_kind(say('MAYA', 'Is it?'), say('MAYA', 'Yes.')) == 'continue')
        check('gap_kind: a speaker change is question / dense / reaction / handoff, most specific first',
              [gap_kind(say('MAYA', t), say('ALEX', 'Next line here please.')) for t in
               ('Did the boat really move upwind?', 'It was forty-five degrees and two knots today.',
                'Right, okay.', 'The sail is a wing standing up in the wind.')]
              == ['question', 'dense', 'reaction', 'handoff'])
        check('gap_for: relaxed 0.7 for every handoff kind, 0.32 to continue; brisk 0.32 for all',
              [gap_for(say('MAYA', t), say(sp, 'x y z w v u'), 'relaxed') for t, sp in
               (('Is it?', 'ALEX'), ('One two three.', 'ALEX'), ('A long enough line of words.', 'ALEX'),
                ('Is it?', 'MAYA'))] == [0.7, 0.7, 0.7, 0.32]
              and {gap_for(say('MAYA', 'Is it?'), say(sp, 'x'), 'brisk') for sp in ('MAYA', 'ALEX')} == {0.32})
        check('spacious: 0.45 within a speaker, 0.91 (relaxed x 1.3) at a handoff, 2.6 s segment',
              [op for op in pace_ops('spacious') if op[0] == 'silence'] ==
              [('silence', x) for x in (0.45, 0.45, 0.91, 0.45, 0.6, 1.2, 0.45, 2.6)])

        check('gap_kind: the question test reads the last sentence, closing quote included',
              [gap_kind(say('MAYA', t), say('ALEX', 'A reply of enough words here.')) for t in
               ('He asked me "does it work?"', 'Is it? I think the boat moves anyway, though.')]
              == ['question', 'handoff'])

        # (K) the lexicon under a splitting pacing: a rule that spans ". " is applied whole
        # (no cut inside a match), and every chunk, with or without an inline pause, is respelled.
        plex_path = os.path.join(td, 'pace-lex.txt')
        with open(plex_path, 'w', encoding='utf-8') as f:
            f.write("U.S. Navy => you ess navy\nGo. Now => go now\nX-team => ex team\n")
        plex = load_lexicon(plex_path, explicit=True)
        plex_script = os.path.join(td, 'pace-lex-script.txt')
        with open(plex_script, 'w', encoding='utf-8') as f:
            f.write("MAYA: Then I said Go. Now we sail. The X-team won. The U.S. Navy watched.\n"
                    "ALEX: Wait. [pause 0.5] The X-team? Sure thing, the X-team.\n")
        for pc in ('relaxed', 'spacious'):
            lev, _ = parse_script(plex_script, voices, *plex, pc)
            chunks = [[v for k, v in line_segments(e) if k == 'text'] for e in lev]
            check(f'{pc} + lexicon: a rule across ". " applies whole; every chunk is respelled',
                  chunks == [['Then I said go now we sail.', 'The ex team won.', 'The you ess navy watched.'],
                             ['Wait.', 'The ex team?', 'Sure thing, the ex team.']])
        blev, _ = parse_script(plex_script, voices, *plex, 'brisk')
        check('brisk + lexicon: the spoken text equals the split pacings\' joined chunks',
              [e[3] for e in blev] == [e[3] for e in parse_script(plex_script, voices, *plex, 'relaxed')[0]])

        # (L) Episode: the one parse -> estimate / pacecheck / plan path main() takes.
        for pc in PACINGS:
            ep = Episode(pace_path, voices, *nolex, pc)
            ev_pc, ch_pc = parse_script(pace_path, voices, *nolex, pc)
            fake_d = lambda sp, text: len(text) / 10.0
            check(f'Episode({pc}): estimate, pacecheck and plan all use {pc}',
                  ep.estimate() == estimate_seconds(ev_pc, pc)
                  and ep.pacecheck()['total_secs'] == pacecheck(ev_pc, ch_pc, pacing=pc)['total_secs']
                  and ep.plan(fake_d) == plan_assembly(ev_pc, ch_pc, fake_d, pacing=pc))
        ep_b, ep_r = Episode(pace_path, voices, *nolex, 'brisk'), Episode(pace_path, voices, *nolex, 'relaxed')
        check('Episode: brisk and relaxed differ in estimate, pacecheck and plan',
              ep_b.estimate()[0] != ep_r.estimate()[0]
              and ep_b.pacecheck()['total_secs'] != ep_r.pacecheck()['total_secs']
              and ep_b.plan(lambda sp, t: 1.0)[0] != ep_r.plan(lambda sp, t: 1.0)[0])

        # (D) a --- divider: 1.1 / 2.0 / 2.6 s by pacing, and still a SegmentBreak for pacecheck.
        seg_events = [('say', 'MAYA', 'Hi.', 'Hi.'), ('pause', SegmentBreak(SEGMENT_GAP)), ('say', 'ALEX', 'Ok.', 'Ok.')]
        check('segment gap per pacing: brisk 1.1, relaxed 2.0, spacious 2.6',
              [plan_assembly(seg_events, [], lambda sp, t: 0.0, pacing=pc)[0][1] for pc in PACINGS]
              == [('silence', 1.1), ('silence', 2.0), ('silence', 2.6)])

        # (E) the cache: gaps are not in the key, so relaxed <-> spacious and brisk -> brisk
        # synthesise nothing new; brisk -> relaxed synthesises the new sentence chunks once.
        def synth_counter():
            seen, calls = set(), [0]

            def synth(sp, text):
                key = cache_key('fake', voices[sp], 24000, 1.0, text)
                if key not in seen:
                    seen.add(key)
                    calls[0] += 1
                return 1.0
            return synth, calls
        synth, calls = synth_counter()
        counts = []
        for pc in ('brisk', 'brisk', 'relaxed', 'spacious', 'relaxed', 'brisk'):
            calls[0] = 0
            pace_ops(pc, fn=synth)
            counts.append(calls[0])
        check('cache: synth calls brisk 6, brisk again 0, relaxed 6 new sentence chunks, spacious 0, '
              'relaxed 0, brisk 0', counts == [6, 0, 6, 0, 0, 0])
        check('cache: no gap or pacing in the cache key (CACHE_VERSION is trim-only)',
              CACHE_VERSION == f'trim{TRIM_THRESHOLD_DB}dB-{TRIM_PAD[0]}-{TRIM_PAD[1]}')

        # (F) the estimate is the planned timeline at WPM, for every pacing.
        for pc in PACINGS:
            ev, ch = parse_script(pace_path, voices, *nolex, pc)
            ops = plan_assembly(ev, ch, lambda sp, text: speech_seconds(text), pacing=pc)[0]
            want = sum(speech_seconds(o[2]) if o[0] == 'say' else o[1] for o in ops)
            check(f'estimate_seconds({pc}) equals its planned timeline',
                  abs(estimate_seconds(ev, pc)[0] - want) < 1e-9)
        # (F2) the speech model itself: per-chunk words/WPM + CHUNK_OVERHEAD, floored; and it stays
        # within 5% of ffprobe on four measured relaxed renders (words, chunks, gap seconds from
        # this parser, measured seconds; two-host kokoro, 2026-10).
        check('speech_seconds: a 40-word chunk is words/WPM + CHUNK_OVERHEAD',
              abs(speech_seconds(' '.join(['w'] * 40)) - (40 / WPM * 60.0 + CHUNK_OVERHEAD)) < 1e-9)
        check('speech_seconds: a one-word chunk is floored, never ~0', speech_seconds('Huh.') == MIN_CHUNK_SECONDS)
        check('speech_seconds: splitting 20+20 words into two chunks costs one more CHUNK_OVERHEAD',
              abs(2 * speech_seconds(' '.join(['w'] * 20)) - speech_seconds(' '.join(['w'] * 40)) - CHUNK_OVERHEAD) < 1e-9)
        for words, chunks, gaps, measured in ((375, 37, 15.7, 136.13), (730, 103, 58.8, 281.23),
                                              (1710, 187, 102.18, 691.78), (1546, 137, 73.68, 596.50)):
            model = words / WPM * 60.0 + chunks * CHUNK_OVERHEAD + gaps
            check(f'speech model within 5% of a measured relaxed render ({words} words: '
                  f'{model:.0f} s vs {measured:.0f} s)', abs(model / measured - 1) < 0.05)
        est = {pc: estimate_seconds(parse_script(pace_path, voices, *nolex, pc)[0], pc)[0] for pc in PACINGS}
        check('estimate: brisk < relaxed < spacious', est['brisk'] < est['relaxed'] < est['spacious'])
        pc_r = pacecheck(*parse_script(pace_path, voices, *nolex, 'relaxed'), pacing='relaxed')
        check('pacecheck(relaxed): totals match the relaxed estimate; sentence gaps are not pauses',
              abs(pc_r['total_secs'] - est['relaxed']) < 1e-9
              and pc_r['pauses'] == pacecheck(*parse_script(pace_path, voices, *nolex, 'brisk'))['pauses'] == 2)

        # (J) relaxed on a turn-form script = brisk on the same script written one sentence
        # per line with [pause 0.7] at each speaker change (how the approved v6 was made).
        turns_path = os.path.join(td, 'turns.txt')
        lines_path = os.path.join(td, 'lines.txt')
        with open(turns_path, 'w', encoding='utf-8') as f:
            f.write("MAYA: Can a boat point at the wind? No. Not quite.\n"
                    "ALEX: Huh. [pause 0.7] So it... zigzags? Each turn is a tack.\n[pause 1.2]\n"
                    "MAYA: Exactly. Under sail, it's the only way.\n")
        with open(lines_path, 'w', encoding='utf-8') as f:
            f.write("MAYA: Can a boat point at the wind?\nMAYA: No.\nMAYA: Not quite.\n[pause 0.7]\n"
                    "ALEX: Huh. [pause 0.7] So it... zigzags?\nALEX: Each turn is a tack.\n[pause 1.2]\n"
                    "MAYA: Exactly. Under sail, it's the only way.\n")
        check('relaxed on turns == brisk on one-sentence lines + [pause 0.7] handoffs (the v6 recipe)',
              pace_ops('relaxed', turns_path) == pace_ops('brisk', lines_path))

        # (G) pacing resolution: --pacing > config default_pacing; bare checkout is brisk.
        class _PaceCfg:
            def __init__(self, value):
                self.value = value

            def load(self):
                return {'default_pacing': self.value}
        check('resolve_pacing: --pacing wins over config',
              resolve_pacing('spacious', which_config=_PaceCfg('brisk')) == 'spacious')
        check('resolve_pacing: config default_pacing used when --pacing is absent',
              resolve_pacing(None, which_config=_PaceCfg('brisk')) == 'brisk')
        check('resolve_pacing: no config.py (bare checkout) is brisk, 0.2.0 timing',
              resolve_pacing(None, which_config=None) == 'brisk')
        err_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(err_buf):
                resolve_pacing(None, which_config=_PaceCfg('fast'))
            check('resolve_pacing: a bad configured value exits 2', False)
        except SystemExit as e:
            check('resolve_pacing: a bad configured value exits 2 naming brisk, relaxed, spacious',
                  e.code == 2 and 'brisk, relaxed, spacious' in err_buf.getvalue())

        # (H) the CLI: --pacing is validated, the dry run reports per pacing, a missing script is exit 2.
        def dry(*extra):
            return subprocess.run([sys.executable, __file__, *extra], capture_output=True, text=True)
        r_bad = dry(pace_path, '--dry-run', '--pacing', 'fast')
        check('--pacing fast exits 2 naming brisk, relaxed, spacious',
              r_bad.returncode == 2 and all(x in r_bad.stderr for x in ('brisk', 'relaxed', 'spacious')))
        outs = {pc: dry(pace_path, '--dry-run', '--pacing', pc) for pc in PACINGS}
        check('--dry-run --pacing: exit 0 and names the pacing it estimated',
              all(o.returncode == 0 and f'({pc} pacing)' in o.stdout for pc, o in outs.items()))
        # The printed estimate and pacecheck segment time are the pacing's own, so main()
        # cannot drop the pacing on the way (parse, estimate or pacecheck).
        long_path = os.path.join(td, 'long.txt')
        with open(long_path, 'w', encoding='utf-8') as f:
            f.write('# ── 1. Long ──\n' + ''.join(
                f"{('MAYA', 'ALEX')[k % 2]}: The boat turns into the wind here. It slows down a lot. "
                f"Then the sail fills again.\n" for k in range(12)))
        printed, expected = {}, {}
        for pc in PACINGS:
            o = dry(long_path, '--dry-run', '--pacing', pc, '--voices', 'MAYA=af_heart,ALEX=am_michael',
                    '--lexicon', plex_path)
            est_line = next((l for l in o.stdout.splitlines() if l.startswith('estimated duration:')), '')
            seg_line = next((l for l in o.stdout.splitlines() if l.startswith('  seg 1')), '')
            printed[pc] = (est_line.split()[2:3], seg_line.split()[4:5])
            lev, lch = parse_script(long_path, voices, *plex, pc)
            expected[pc] = ([fmt_mmss(estimate_seconds(lev, pc)[0])],
                            [fmt_mmss(pacecheck(lev, lch, pacing=pc)['segments'][0]['secs'])])
        check(f'--dry-run prints each pacing\'s own estimate and segment time ({printed})',
              printed == expected and printed['brisk'] != printed['relaxed'] != printed['spacious'])
        r_missing = dry(os.path.join(td, 'nope-script.txt'), '--dry-run', '--pacing', 'brisk')
        check('a missing script exits 2 with a message, no traceback',
              r_missing.returncode == 2 and 'not found' in r_missing.stderr
              and 'Traceback' not in r_missing.stderr)

        # Tier 0: --dry-run parses and estimates inline pauses with no engine imported.
        dr = subprocess.run([sys.executable, __file__, inline_path, '--dry-run',
                             '--voices', 'MAYA=af_heart,ALEX=am_michael', '--lexicon', lex_path],
                            capture_output=True, text=True)
        check('--dry-run handles inline pauses (exit 0, 14 spoken words)',
              dr.returncode == 0 and '3 dialogue lines, 14 spoken words' in dr.stdout)

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

    # ---- pacecheck: one fixture per metric, one per warning kind (fictional topic) ----
    with tempfile.TemporaryDirectory() as ptd:
        no_lex = load_lexicon(None)

        def pace_parse(name, text):
            path = os.path.join(ptd, name)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            return path, parse_script(path, voices, *no_lex)

        def kinds(pc):
            return [k for k, _ in pc['warnings']]

        LONG = 'The colony keeps its brood close to the warm centre of the comb.'  # 13 words
        SHORT = 'Bees fan the brood.'  # 4 words

        check('split_sentences: ends at . ? !, not at a "..." hold',
              split_sentences('So there\'s... no path. And it lifts? Yes! Done') ==
              ["So there's... no path.", 'And it lifts?', 'Yes!', 'Done'])
        check('SegmentBreak: equal to SEGMENT_GAP, so events compare as before',
              SegmentBreak(SEGMENT_GAP) == SEGMENT_GAP and ('pause', SegmentBreak(SEGMENT_GAP)) == ('pause', SEGMENT_GAP))

        # Clean fixture: two segments, a pause in each, MAYA tells both, one sound in front of
        # words, and a short-sentence share at the middle of FLAT_LINES_BAND.
        lo, hi = FLAT_LINES_BAND
        mid = (lo + hi) / 2
        seg1 = ['ALEX: Why do the bees huddle up in winter?', f'MAYA: {LONG} {LONG}', '[pause 1]',
                'ALEX: Hmm. [pause 0.6] So the middle of the cluster stays warm?']
        seg2 = ['MAYA: And what changes once spring finally arrives?', f'ALEX: {LONG} [pause 0.8] {LONG}']

        def build_clean(t1, t2, asker2='ALEX', teller2='MAYA'):
            seg2 = [f'{asker2}: And what changes once spring finally arrives?',
                    f'{teller2}: {LONG} [pause 0.8] {LONG}']
            return '\n'.join(['# ── 1. Winter ──'] + seg1 + (['MAYA: ' + ' '.join(t1)] if t1 else [])
                             + ['---', '# ── 2. Spring ──'] + seg2
                             + ([f'{teller2}: ' + ' '.join(t2)] if t2 else [])) + '\n'

        tell1, tell2 = [], []
        for _ in range(60):  # top up the tellers' lines until the share sits mid-band
            clean_text = build_clean(tell1, tell2)
            _, (c_events, c_chapters) = pace_parse('clean.txt', clean_text)
            share = pacecheck(c_events, c_chapters)['short_share']
            if abs(share - mid) < 0.04:
                break
            (tell1 if len(tell1) <= len(tell2) else tell2).append(SHORT if share < mid else LONG)
        pc = pacecheck(c_events, c_chapters)
        check('pacecheck: the clean fixture has no warnings', pc['warnings'] == [])
        check('pacecheck: lines counted', pc['lines'] == sum(1 for e in c_events if e[0] == 'say'))
        check('pacecheck: inline and whole-line pauses count, a --- divider does not', pc['pauses'] == 3)
        check('pacecheck: secs_per_pause = estimate / pauses',
              abs(pc['secs_per_pause'] - estimate_seconds(c_events)[0] / 3) < 1e-9)
        check('pacecheck: roles fixed (MAYA tells both segments, ALEX learns)',
              [(s['teller'], s['listener']) for s in pc['segments']] == [('MAYA', 'ALEX'), ('MAYA', 'ALEX')])
        check('pacecheck: one sound counted, in segment 1', pc['nonlexical'] == 1 and pc['sounds'] == {'hmm': 1}
              and [s['nonlexical'] for s in pc['segments']] == [1, 0])
        check('pacecheck: the timeline (via plan_assembly) adds up to estimate_seconds()',
              abs(sum(t[2] for t in _pace_timeline(c_events, c_chapters)) - estimate_seconds(c_events)[0]) < 1e-6)

        # Metric fixture: exact numbers.
        _, (m_events, m_chapters) = pace_parse('metrics.txt',
            'MAYA: One two three. Four five six seven eight nine ten.\n'      # 10 words, sentences 3 + 7
            'MAYA: Eleven twelve... thirteen?\n'                               # 3 words, one sentence
            '[pause 2]\n'
            'ALEX: Uh-huh, ha. [pause 0.5] Twenty percent of 40 hives.\n'     # 8 words, sounds uh-huh + ha
            '---\n'
            'ALEX: Fine.\n')                                                   # 1 word, new segment
        pc = pacecheck(m_events, m_chapters)
        # sentences: 3 | 7 | "Eleven twelve... thirteen?" 3 | "Uh-huh, ha." 2 | 5 | "Fine." 1
        check('pacecheck: sentence share (5 of 6 sentences are <= 6 words; "..." is not an end)',
              pc['sentences'] == 6 and abs(pc['short_share'] - 5 / 6) < 1e-9)
        import statistics
        check('pacecheck: avg and sd of words per line', abs(pc['avg_words'] - (10 + 3 + 7 + 1) / 4) < 1e-9
              and abs(pc['sd_words'] - statistics.pstdev([10, 3, 7, 1])) < 1e-9)
        check('pacecheck: longest pause-free stretch = speech + turn gaps before the [pause 2]',
              abs(pc['longest_pause_free'][0] - (_ref_speech(10, 3) + TURN_GAP)) < 1e-9)
        check('pacecheck: longest run is MAYA, 13 words, from event 0', pc['longest_run'] == ('MAYA', 13, 0))
        check('pacecheck: "uh-huh" counts once (not also as "huh"), "ha" counts',
              pc['sounds'] == {'uh-huh': 1, 'ha': 1})
        check('pacecheck: figures/min counts number words and digits',
              abs(pc['figures_per_min'] - 12 / (estimate_seconds(m_events)[0] / 60.0)) < 1e-9)
        check('pacecheck: a script with no chapters still splits at --- (2 segments)', len(pc['segments']) == 2)
        check('pacecheck: no sound list (bare checkout) counts nothing',
              pacecheck(m_events, m_chapters, nonlexical={})['nonlexical'] == 0)

        # One fixture per warning kind.
        long_para = ' '.join([LONG] * 8)  # 104 words, ~40 s
        _, (e, ch) = pace_parse('nopause_rate.txt', f'MAYA: {long_para}\nALEX: {long_para}\nMAYA: {long_para}\n')
        check('NO_PAUSE: no pause over > 90 s warns (rate)', 'NO_PAUSE' in kinds(pacecheck(e, ch)))
        _, (e, ch) = pace_parse('nopause_stretch.txt',
                                '[pause 1]\n[pause 1]\n[pause 1]\n'
                                + ''.join(f'{"MAYA" if k % 2 else "ALEX"}: {long_para}\n' for k in range(5))
                                + '[pause 1]\n' * 3)
        pc = pacecheck(e, ch)
        check('NO_PAUSE: a 3+ min pause-free stretch warns even when the rate is fine',
              pc['secs_per_pause'] <= PAUSE_EVERY_SECS and 'NO_PAUSE' in kinds(pc))
        _, (e, ch) = pace_parse('longrun.txt', f'MAYA: {LONG} [pause 1] {long_para}\nALEX: {SHORT}\n')
        check('LONG_RUN: one speaker over 90 words warns', 'LONG_RUN' in kinds(pacecheck(e, ch)))
        _, (e, ch) = pace_parse('solo.txt', f'MAYA: {LONG} [pause 1] {long_para}\n')
        check('LONG_RUN: a one-voice script is exempt', 'LONG_RUN' not in kinds(pacecheck(e, ch)))
        n_min = FLAT_LINES_MIN_SENTENCES
        _, (e, ch) = pace_parse('flat.txt', ''.join(f'[pause 1]\n{"MAYA" if k % 2 else "ALEX"}: {LONG}\n'
                                                    for k in range(n_min)))
        check('FLAT_LINES: no short sentences warns', 'FLAT_LINES' in kinds(pacecheck(e, ch)))
        _, (e, ch) = pace_parse('choppy.txt', ''.join(f'[pause 1]\n{"MAYA" if k % 2 else "ALEX"}: {SHORT}\n'
                                                      for k in range(n_min)))
        check('FLAT_LINES: all short sentences warns too', 'FLAT_LINES' in kinds(pacecheck(e, ch)))
        _, (e, ch) = pace_parse('tiny.txt', ''.join(f'[pause 1]\n{"MAYA" if k % 2 else "ALEX"}: {LONG}\n'
                                                    for k in range(n_min - 1)))
        check('FLAT_LINES: fewer than FLAT_LINES_MIN_SENTENCES sentences is not judged',
              'FLAT_LINES' not in kinds(pacecheck(e, ch)))
        # Per segment: a flat second segment warns by name even when the episode share is fine.
        mixed = (''.join(f'[pause 1]\nMAYA: {SHORT} {SHORT}\nALEX: {LONG}\n' for _ in range(n_min // 2))
                 + '---\n# ── 2. Drones ──\n'
                 + ''.join(f'[pause 1]\n{"MAYA" if k % 2 else "ALEX"}: {LONG}\n' for k in range(n_min)))
        _, (e, ch) = pace_parse('flatseg.txt', mixed)
        pc = pacecheck(e, ch)
        check('FLAT_LINES: judged per segment, naming the flat one',
              [m for k, m in pc['warnings'] if k == 'FLAT_LINES'] ==
              [f'segment 2 "2. Drones": 0% of {n_min} sentences are {SHORT_SENTENCE_WORDS} words or fewer '
               f'(aim for {FLAT_LINES_BAND[0]:.0%}-{FLAT_LINES_BAND[1]:.0%})'])
        # TELLER_CHANGED: two-host roles are fixed. Episodes of cold open, three body segments and a wrap.
        def roles_seg(n, title, teller, learner=None):
            head = [f'# ── {n}. {title} ──']
            if teller is None:  # roles unclear: two equal turns, no question, no short turn
                return head + [f'MAYA: {LONG}', f'ALEX: {LONG}', '[pause 1]', '---']
            return head + [f'{learner}: Why do the bees huddle up in winter?', f'{teller}: {SHORT} {SHORT} {LONG}',
                           '[pause 1]', f'{learner}: So the middle stays warm?', f'{teller}: {SHORT} {LONG}', '---']

        def roles_ep(name, tellers, cold='ALEX', wrap='ALEX'):
            hosts = {'MAYA': 'ALEX', 'ALEX': 'MAYA'}
            segs = [roles_seg(1, 'Cold open', cold, hosts[cold])]
            segs += [roles_seg(k + 2, f'Part {k + 1}', t, hosts.get(t)) for k, t in enumerate(tellers)]
            segs += [roles_seg(len(tellers) + 2, 'Wrap', wrap, hosts[wrap])]
            text = '\n'.join(line for seg in segs for line in seg) + '\n'
            return pacecheck(*pace_parse(name, text)[1]), text

        changed = lambda pc: [m for k, m in pc['warnings'] if k == 'TELLER_CHANGED']
        pc, _ = roles_ep('fixedroles.txt', ['MAYA', 'MAYA', 'MAYA'])
        check('TELLER_CHANGED: fixed roles are clean, though ALEX tells the cold open and the wrap',
              [s['teller'] for s in pc['segments']] == ['ALEX', 'MAYA', 'MAYA', 'MAYA', 'ALEX']
              and pc['warnings'] == [])
        pc, swap_text = roles_ep('swaproles.txt', ['MAYA', 'ALEX', 'MAYA'])
        check('TELLER_CHANGED: a teller swap every segment warns on the odd one out, by name',
              [s['teller'] for s in pc['segments']] == ['ALEX', 'MAYA', 'ALEX', 'MAYA', 'ALEX'] and changed(pc) ==
              ['segment 3 "3. Part 2": ALEX tells, but MAYA tells 2 of 3 body segments; keep one teller all episode'])
        pc, _ = roles_ep('unclearroles.txt', ['MAYA', None, 'ALEX'])
        check('TELLER_CHANGED: a "roles unclear" segment is neither judged nor counted (a 1-1 tie goes to the earliest)',
              pc['segments'][2]['teller'] is None and changed(pc) ==
              ['segment 4 "4. Part 3": ALEX tells, but MAYA tells 1 of 2 body segments; keep one teller all episode'])
        pc, _ = roles_ep('unclearonly.txt', ['MAYA', None, 'MAYA'])
        check('TELLER_CHANGED: fixed roles around a "roles unclear" segment stay clean',
              pc['segments'][2]['teller'] is None and changed(pc) == [])
        # On a three-voice panel the guests take turns telling by design: never judged.
        panel = swap_text.replace('ALEX: Why do the bees', 'IRIS: Why does this matter? \nALEX: Why do the bees')
        with open(os.path.join(ptd, 'panelteller.txt'), 'w', encoding='utf-8') as f:
            f.write(panel)
        pc = pacecheck(*parse_script(os.path.join(ptd, 'panelteller.txt'), {**voices, 'IRIS': 'af_bella'}, *no_lex))
        check('TELLER_CHANGED: not judged on a three-voice script',
              panel.count('IRIS:') >= 2 and [s['teller'] for s in pc['segments']][1:4] == ['MAYA', 'ALEX', 'MAYA']
              and 'TELLER_CHANGED' not in kinds(pc))
        _, (e, ch) = pace_parse('alone.txt', clean_text.replace('ALEX: Hmm. [pause 0.6] So the', 'ALEX: Hmm.\nALEX: So the'))
        check('NONLEXICAL_ALONE: a sound on its own line warns', 'NONLEXICAL_ALONE' in kinds(pacecheck(e, ch)))
        _, (e, ch) = pace_parse('alone2.txt', clean_text.replace('[pause 0.6] So the', '[pause 0.6] Huh.\nALEX: So the'))
        check('NONLEXICAL_ALONE: sounds split only by an inline pause still warn',
              'NONLEXICAL_ALONE' in kinds(pacecheck(e, ch)))
        _, (e, ch) = pace_parse('many.txt', clean_text.replace('Why do the bees', 'Huh. Why do the bees'))
        check('NONLEXICAL_MANY: two sounds in one segment warns', 'NONLEXICAL_MANY' in kinds(pacecheck(e, ch)))
        check('pacecheck: warning kinds come from the fixed list', set(PACE_KINDS) == {
            'NO_PAUSE', 'LONG_RUN', 'FLAT_LINES', 'TELLER_CHANGED', 'NONLEXICAL_ALONE', 'NONLEXICAL_MANY',
            'BANNED_SOUND'})

        # A paced segment followed by an unpaced one, inside one episode: the episode rate
        # is fine, but segment 2 (> 90 s, no pause) must still warn, by name.
        paced = ''.join(f'[pause 1]\n{"MAYA" if k % 2 else "ALEX"}: {LONG}\n' for k in range(24))
        combo = ('# ── 1. Winter ──\n' + paced + '---\n# ── 2. Swarming ──\n'
                 + ''.join(f'{"MAYA" if k % 2 else "ALEX"}: {LONG}\n' for k in range(24)))
        _, (e, ch) = pace_parse('combo.txt', combo)
        pc = pacecheck(e, ch)
        check('NO_PAUSE: an unpaced segment inside a paced episode warns, naming segment 2',
              pc['secs_per_pause'] <= PAUSE_EVERY_SECS and pc['segments'][1]['secs'] > PAUSE_EVERY_SECS
              and pc['segments'][1]['longest_pause_free'] <= MAX_PAUSE_FREE_SECS
              and [m.split(':')[0] for k, m in pc['warnings'] if k == 'NO_PAUSE'] == ['segment 2 "2. Swarming"'])
        check('pacecheck: a closing --- divider is not counted as pause-free speech',
              abs(pc['segments'][0]['longest_pause_free'] - _ref_speech(13)) < 1e-9)

        # Roles are scored per TURN: a teller writing one short sentence per line is still the teller.
        _, (e, ch) = pace_parse('turns.txt',
            'ALEX: Why do the bees huddle up so close in the winter?\n'
            + f'MAYA: {SHORT}\n' * 6
            + 'ALEX: And how do they keep the queen warm through it all?\n'
            + f'MAYA: {SHORT}\n' * 3)
        pc = pacecheck(e, ch)
        check('roles: consecutive one-sentence lines merge into one turn (MAYA tells)',
              (pc['segments'][0]['teller'], pc['segments'][0]['listener']) == ('MAYA', 'ALEX'))
        # Short turns alone (no "?") mark the listener.
        _, (e, ch) = pace_parse('shortturns.txt', f'MAYA: {LONG}\nALEX: Right.\nMAYA: {LONG}\n'
                                                  f'ALEX: Okay, go on.\nMAYA: {LONG}\n')
        pc = pacecheck(e, ch)
        check('roles: short turns count toward the listener without any "?"',
              (pc['segments'][0]['teller'], pc['segments'][0]['listener']) == ('MAYA', 'ALEX'))
        # Three voices: a tie at the top means no listener, a unique bottom is still the teller.
        voices3 = dict(voices, JO='af_bella')
        p3 = os.path.join(ptd, 'panel.txt')
        with open(p3, 'w', encoding='utf-8') as f:
            f.write(f'MAYA: {LONG}\nALEX: Why though?\nMAYA: {LONG}\nJO: Why?\n')
        pc = pacecheck(*parse_script(p3, voices3, *no_lex))
        check('roles: a tie for listener gives no listener; the unique teller stays',
              (pc['segments'][0]['teller'], pc['segments'][0]['listener']) == ('MAYA', None))
        # Runs end at a segment boundary.
        half = ' '.join([LONG] * 4)  # 52 words
        _, (e, ch) = pace_parse('runseg.txt', f'ALEX: {SHORT}\nMAYA: {half}\n---\nMAYA: {half}\nALEX: {SHORT}\n')
        pc = pacecheck(e, ch)
        check('LONG_RUN: a run does not continue across a segment boundary',
              pc['longest_run'][:2] == ('MAYA', 52) and 'LONG_RUN' not in kinds(pc))
        # Warnings are ordered by kind (PACE_KINDS), not by when they were found.
        _, (e, ch) = pace_parse('order.txt', 'ALEX: Hmm.\n' + ''.join(
            f'{"MAYA" if k % 2 else "ALEX"}: {LONG}\n' for k in range(30)))
        ks = kinds(pacecheck(e, ch))
        check('pacecheck: warnings sorted by kind (NO_PAUSE before NONLEXICAL_ALONE)',
              ks[0] == 'NO_PAUSE' and 'NONLEXICAL_ALONE' in ks
              and ks == sorted(ks, key=PACE_KINDS.index))
        # Sounds: a repeat is one sound; every m-spelling of "mm-hm" is BANNED_SOUND.
        snd = {'ha': [], 'huh': [], 'uh-huh': []}
        check('find_sounds: "Ha-ha" is one sound', find_sounds('Ha-ha. So?', snd)[0] == ['ha'])
        check('find_sounds: "ha ha" is one sound', find_sounds('Ha ha, so?', snd)[0] == ['ha'])
        check('find_sounds: "uh-huh" is not also a "huh"', find_sounds('Uh-huh. Huh.', snd)[0] == ['uh-huh', 'huh'])
        for bad in ('Mm-hm', 'Mhm', 'Mmhmm', 'Mm'):
            _, (e, ch) = pace_parse('banned.txt', f'[pause 1]\nMAYA: {LONG}\nALEX: {bad}. So the cluster stays warm?\n')
            check(f'BANNED_SOUND: {bad!r} warns', 'BANNED_SOUND' in kinds(pacecheck(e, ch)))
        _, (e, ch) = pace_parse('notbanned.txt', f'[pause 1]\nMAYA: {LONG}\nALEX: Hmm. Mmm-good honey, hmm?\n')
        check('BANNED_SOUND: "hmm" and an "mm" inside a word do not warn',
              'BANNED_SOUND' not in kinds(pacecheck(e, ch)))

        # CLI: --dry-run --strict exits 4 on a warning, 0 when clean; --strict alone is bad input.
        def run_cli(path, *extra):
            r = subprocess.run([sys.executable, os.path.abspath(__file__), path, '--dry-run',
                                '--voices', 'MAYA=af_heart,ALEX=am_michael', *extra],
                               capture_output=True, text=True, encoding='utf-8')
            return r.returncode, r.stdout
        code, out = run_cli(os.path.join(ptd, 'nopause_rate.txt'), '--strict')
        check('--dry-run --strict exits 4 on a NO_PAUSE fixture', code == STRICT_EXIT == 4 and '⚠ NO_PAUSE:' in out)
        code, out = run_cli(os.path.join(ptd, 'nopause_rate.txt'))
        check('--dry-run without --strict still exits 0 and prints the warning', code == 0 and '⚠ NO_PAUSE:' in out)
        code, out = run_cli(os.path.join(ptd, 'clean.txt'), '--strict')
        check('--dry-run --strict exits 0 on the clean fixture', code == 0 and out.count('\npacecheck  ') == 1
              and '⚠' not in out)
        r = subprocess.run([sys.executable, os.path.abspath(__file__), os.path.join(ptd, 'clean.txt'),
                            os.path.join(ptd, 'x.mp3'), '--strict'], capture_output=True, text=True)
        check('--strict without --dry-run is bad input (exit 2), never 3', r.returncode == 2)
        probe = ("import runpy, sys\n"
                 f"sys.argv = [{os.path.abspath(__file__)!r}, {os.path.join(ptd, 'clean.txt')!r}, '--dry-run', '--strict']\n"
                 "try:\n    runpy.run_path(sys.argv[0], run_name='__main__')\nexcept SystemExit:\n    pass\n"
                 "print(sorted(m for m in ('numpy', 'soundfile', 'kokoro', 'kokoro_onnx', 'onnxruntime',"
                 " 'torch', 'piper') if m in sys.modules))\n")
        r = subprocess.run([sys.executable, '-c', probe], capture_output=True, text=True, encoding='utf-8')
        check('--dry-run (with pacecheck) imports no engine, numpy or soundfile',
              r.returncode == 0 and r.stdout.strip().endswith('[]'))

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


def resolve_pacing(cli_pacing, which_config=_UNSET):
    """--pacing > config.load()['default_pacing']. Without config.py (a bare checkout) the
    default is brisk, i.e. 0.2.0's timing. A bad configured value exits 2 naming the set."""
    if cli_pacing:
        return cli_pacing
    cfg = config if which_config is _UNSET else which_config
    if cfg is None:
        return 'brisk'
    pacing = cfg.load().get('default_pacing', 'relaxed')
    if pacing not in PACINGS:
        die(f'default_pacing {pacing!r} is not one of {", ".join(PACINGS)} '
            f'(fix: config.py set default_pacing=relaxed)', 2)
    return pacing


def main():
    ap = build_arg_parser()
    args = ap.parse_args()

    if args.selftest:
        sys.exit(run_selftest())

    if not args.script:
        ap.error('the following arguments are required: script')
    if args.strict and not args.dry_run:
        ap.error('--strict only applies to --dry-run (pacecheck)')
    if not os.path.isfile(args.script):
        die(f'{args.script}: script file not found', 2)
    pacing = resolve_pacing(args.pacing)

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
    episode = Episode(args.script, voices, pattern, rules, pacing)
    events, chapters = episode.events, episode.chapters

    if args.dry_run:
        total, starts = episode.estimate()
        say_lines = [e for e in events if e[0] == 'say']
        word_count = sum(len(e[3].split()) for e in say_lines)
        print(f'{len(say_lines)} dialogue lines, {word_count} spoken words')
        print(f'estimated duration: {fmt_mmss(total)} ({total / 60:.1f} min) at {WPM} wpm, {CHUNK_OVERHEAD:+.2f} s per chunk, + gaps '
              f'({pacing} pacing)')
        if chapters:
            print('chapters:')
            for title, idx in chapters:
                print(f'  {fmt_mmss(starts[idx])}  {title}')
        else:
            print('chapters: none')
        pc = episode.pacecheck()
        print_pacecheck(pc)
        if args.strict and pc['warnings']:
            sys.exit(STRICT_EXIT)
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

    # plan_assembly() lays out the timeline (selftested without an engine); synthesis
    # happens in its duration callback, and the ops are then executed in order.
    chunk_audio = {}
    said = 0

    def chunk_seconds(speaker, spoken_text):
        audio = say(speaker, spoken_text)
        chunk_audio[(speaker, spoken_text)] = audio
        return len(audio) / sr

    def progress():
        nonlocal said
        said += 1
        print(f'\r  {said} lines', end='', flush=True)

    ops, chapter_records = episode.plan(chunk_seconds, progress)
    parts = [chunk_audio[(op[1], op[2])] if op[0] == 'say'
             else np.zeros(int(op[1] * sr), dtype=np.float32) for op in ops]

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
          f'{len(chapter_records)} chapters  ({engine.name}, {sr} Hz, {pacing} pacing{cast_note}){pace_note}')


if __name__ == '__main__':
    main()
