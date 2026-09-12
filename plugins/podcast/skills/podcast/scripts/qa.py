#!/usr/bin/env python3
"""
qa.py: pronunciation/coverage QA for a rendered podcast episode.

Transcribes AUDIO with one of two backends (unless --transcript is given), aligns
the heard text against SCRIPT's dialogue lines (written form, before any lexicon
substitution — whisper should hear the true word) with difflib, and reports words
that were likely mispronounced, dropped, duplicated, swapped, or invented.

Backend A is `whisper-cli` (whisper.cpp): used if configured via config.py or found
on PATH, with a ggml model file resolved from the state models dir (or --model as an
explicit path). Backend B is faster-whisper, run as a subprocess of the installer-
managed venv's python (config.venv_python()) rather than imported directly, so this
file itself stays stdlib-only. Backend A is tried first; whichever backend actually
runs, its model/size level comes from config.load()['qa_level'] / detect()['qa_active'],
overridable with --model (a ggml path for backend A, a size level like "small" for
backend B). If neither backend is available, exits 3 with an upgrade hint --
distinct from a failed QA gate (1) and a tool/IO error (2).

  python3 bin/qa.py SCRIPT AUDIO [--transcript FILE] [--lexicon FILE] [--ignore FILE]
      [--model PATH-or-LEVEL] [--json OUT] [--threshold 0.96]
      [--min-coverage-tokens 150] [--selftest]

Default --threshold is 0.96: five real whisper decodes of a clean render scored
0.980-0.985, and a scattered-small-loss pattern (a 3-word run gone from ~45% of
lines, or six words collapsed into one garbled word on ~22% of lines -- about 55s
of missing audio either way) lands right at 0.930, so 0.93 let it through.

The coverage/--threshold gate only APPLIES at or above --min-coverage-tokens
(default 150 normalized expected tokens, see MIN_COVERAGE_TOKENS) -- below that,
coverage is a noisy rate: a 20-token smoke-test script that suppresses one benign
transcription variant ("plugin"/"plug-in") loses 5% of its tokens on that account
alone, enough to trip the 0.96 default on a script that would score 1.0000 on
re-render, while the same variant costs 0.07% on a real ~1,500-word episode.
Below the token floor, coverage is still computed and printed (marked
informational, not gating) and the exit code is decided purely by the structural
gates below (DROPPED/TRUNCATED/MISSING/EXTRA_AUDIO/NAMES/NEGATION), which stay
meaningful at any script length.

Normalization (applied to both sides before alignment, and shown in reports —
mismatches are reported as normalized tokens, not original casing/punctuation, since
normalization is exactly what this tool is judging):
  - lowercase; curly quotes/dashes -> ASCII
  - strip a trailing possessive ('s, or a lone trailing ' for a plural possessive)
    BEFORE splitting into letters, so "C E O's" and "CEO's" both become "ceo"
  - strip remaining punctuation except word-internal apostrophes (don't, isn't); split
    on hyphens
  - drop numeric material: any token containing a digit, plus number words
    (zero..nineteen, twenty..ninety, hundred, thousand, million, billion, trillion,
    point, percent, dollar, dollars, and "and"). Numbers are deliberately not QA'd:
    the script spells them ("twenty twenty-six") and whisper writes digits ("2026").
    Kept simple: "and" is always dropped as numeric-adjacent, not only when it sits
    between two number words -- a handful of legitimate "and"s go uncompared, which
    is the right side to err on for a coverage check.
  - join runs of >=2 consecutive single-letter tokens into one ("C E O" and "CEO"
    both become "ceo")

--lexicon is not applied to the expected text (the script keeps its true spelling).
Instead, each "written => spoken" rule becomes automatic ignore pairs: expected=
written vs heard=spoken (the lexicon fix worked, whisper heard the respelling),
expected=written vs heard=written (whisper still heard the letters as originally
written -- also not a defect), plus a per-word pair for each differing position
when written/spoken have the same word count (difflib usually isolates just the
one changed word, e.g. "X-team"/"ex team" -> only "x" vs "ex" mismatches, since
"team" already matches both sides -- a phrase-level pair alone would rarely fire).

Ignore pairs (both kinds) and the compound/possessive suppressions apply at the
sub-word level even inside a larger mismatch: an op's own expected/heard tokens are
re-aligned, and any piece that is itself an exact pair or concat-equal match is
dropped before anything is reported or gated -- so "Okay, Zenlift" against a
script that says "OK, Zenlyft" is judged only on "Okay"/"OK", not blocked from
suppressing the (already-known-good) Zenlyft/Zenlift part just because they
landed in the same diff block.

Coverage counts only exact (difflib "equal") token matches -- ignore pairs and the
noise suppressions never change the coverage number, only what gets *reported* and
*gated*.

Contractions with n't are expanded to " not" on BOTH sides before comparison
(won't -> will not, can't/cannot -> can not, shan't -> shall not, ain't -> is not,
everything else regular: isn't -> is not, doesn't -> does not, ...), so a
transcript that expands or contracts a negation reads identically to the script.

Beyond the (size-conditional) coverage gate and DROPPED, six more checks can fail
the run (each gets its own label in the report and in --json) -- these are NOT
conditional on script length, since each already requires its own minimum run
length or count before firing:
  TRUNCATED   a line with >=8 tokens where under 60% of its own tokens matched
              (DROPPED still covers the zero-match case)
  MISSING     any unsuppressed delete run of >=4 normalized words, OR an
              unsuppressed replace whose (post-suppression) expected side has >=4
              more words than its heard side -- a delete catches most losses, but
              a garbled stretch that whisper hears as one wrong word (six words in,
              one word out) is a REPLACE op, invisible to a delete-only check
  EXTRA_AUDIO a replace op whose heard side has >=12 more tokens than its expected
              side, an insert run of >=6 words (repeats, hallucination loops,
              wrong-line audio), or total unmatched heard tokens over 5% of all
              heard tokens
  NAMES       an unsuppressed replace whose leftover expected tokens (after
              sub-word ignore-pair suppression) contain a word that both (a) is
              ever capitalised somewhere OTHER than the first word of a line or
              sentence, or is ALL-CAPS with length > 1 (an acronym is a name
              regardless of position -- "ACRO" only ever opens a sentence here but
              is still a name), and (b) never appears in lowercase anywhere in the
              script. Plain sentence-openers ("Okay", "Employee[s]", "You'll", ...)
              are capitalised by grammar, not because they're names, so
              capitalised-only-at-sentence-start is deliberately NOT sufficient on
              its own -- "a", "we", "team" etc. also fail because they appear
              lowercase elsewhere, and I/I'm/I'd/I'll/I've/single letters are
              excluded outright. Trade-off accepted: a name that only ever opens a
              sentence and is never written in all-caps (e.g. "Robin",
              "Vendorly" in this episode) is missed.
  NEGATION    a non-equal op (replace/delete/insert) where the count of negation
              words (not/no/never/nor/none/nobody/nothing/neither/without) differs
              between its expected and heard sides, in either direction -- catches
              an added, dropped, or swapped negation even as a single token, but
              not a contraction that expands/contracts (both sides already read
              "not" after normalization)
  (coverage/--threshold: gates only at/above --min-coverage-tokens; see above)

A replace/delete op that spans more than one script line is reported once, against
the full line range it touches ("L116-L117"), rather than guessing a per-line split
of the heard side -- there is no way to know which half of a merged mismatch belongs
to which line, so we say what we actually know.

Known limitations (accepted, no fix planned):
  - NAMES misses a name that only ever opens a sentence and is never written in
    all-caps (see above -- "Robin", "Vendorly" in the current episode).
  - partition_leftover's nested-diff fallback (used when an ignore-pair match would
    need to span an op whose expected/heard word counts differ) can fail to find a
    known-good pair if there's no shared token for it to anchor on -- e.g. "xoom"
    heard as "zoom so" (an ignore pair for "xoom"~"zoom" exists, but the extra "so"
    shifts the op to unequal length and the nested SequenceMatcher has nothing
    identical between ('xoom',) and ('zoom','so') to align around). The equal-
    length, positional-zip path (the common case, and the one the "Okay, Zenlift"
    fix targets) is exact; only this unequal-length fallback can miss a pair.

Exit codes: 0 = all gates pass; 1 = a gate failed; 2 = tool/IO error (ffmpeg/
transcription-backend failure, missing/undecodable file, a script with no dialogue
lines -- also the signature of SCRIPT/AUDIO swapped on the command line, etc);
3 = no transcription backend installed at all (see "audio QA not installed" above --
neither a gate failure nor a tool error, so a caller can tell "fix your install"
apart from "the render has a real defect").
"""
import argparse, difflib, json, os, re, shutil, subprocess, sys, tempfile

try:
    import config
except ImportError:
    config = None

# Sentinel distinguishing "caller didn't pass which_config" (use the real
# module-level `config`, if importable) from an explicit `which_config=None`
# (selftest's way of simulating "no config module at all").
_UNSET = object()

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(REPO_ROOT, 'templates')


def default_sidecar_path(script_path, filename):
    """<directory of SCRIPT>/filename, falling back to the skill's own
    templates/filename when the episode directory doesn't have its own copy --
    episodes keep their own lexicon.txt/qa-ignore.txt, but a fresh episode dir (or
    one older than this convention) has neither, in which case the skill's
    generic template still applies. Neither existing is unchanged from today:
    load_ignore_file()/load_lexicon_ignore_pairs() silently no-op on a missing
    path (HIGH 3: before this, the default pointed at REPO_ROOT itself, where
    neither file has ever lived -- the pronunciation loop was dead and QA was
    judging every episode with zero lexicon-derived ignore pairs, producing at
    least one false NAMES failure on a real episode)."""
    episode_path = os.path.join(os.path.dirname(os.path.abspath(script_path)) or '.', filename)
    if os.path.exists(episode_path):
        return episode_path
    template_path = os.path.join(TEMPLATES_DIR, filename)
    if os.path.exists(template_path):
        return template_path
    return episode_path  # doesn't exist either; the loaders' no-op handles it

CURLY = str.maketrans({
    '‘': "'", '’': "'", '“': '"', '”': '"',
    '–': '-', '—': '-', '−': '-',
})

NUMBER_WORDS = set('''
    zero one two three four five six seven eight nine ten
    eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen
    twenty thirty forty fifty sixty seventy eighty ninety
    hundred thousand million billion trillion point percent dollar dollars and
'''.split())

NEGATION_WORDS = {"not", "no", "never", "nor", "none", "nobody", "nothing",
                   "neither", "without"}

# n't contractions are expanded to " not" before comparison (both sides), so
# "don't"/"do not" are indistinguishable and a swap can't hide or fabricate a
# negation. Irregular stems are listed explicitly; everything else is the regular
# "<stem>n't" -> "<stem> not" pattern (isn't -> is not, doesn't -> does not, ...).
CONTRACTION_SPECIAL = {"can't": "can not", "won't": "will not", "shan't": "shall not",
                        "ain't": "is not", "cannot": "can not"}
CONTRACTION_SPECIAL_RE = re.compile(r"(?i)\b(can't|won't|shan't|ain't|cannot)\b")
CONTRACTION_GENERIC_RE = re.compile(r"(?i)\b(\w+)n't\b")

TRUNCATED_MIN_TOKENS = 8
TRUNCATED_MAX_MATCH_SHARE = 0.6
EXTRA_AUDIO_PER_OP = 12
EXTRA_AUDIO_INSERT_MIN = 6
EXTRA_AUDIO_GLOBAL_FRACTION = 0.05
MISSING_MIN_TOKENS = 4

# The coverage/--threshold gate is a RATE, so it only means what it claims on a
# script with enough tokens for one benign suppressed variant not to dominate the
# denominator. A 20-token smoke-test script that suppresses one compound-word
# variant ("plugin"/"plug-in") loses 1 of 20 tokens = 5% -- enough to trip the
# 0.96 default threshold on its own, even though the identical script re-rendered
# scored 1.0000; the same single variant in a real ~1,500-word episode costs
# 0.07%. 150 normalized tokens is roughly a minute of spoken content -- comfortably
# past the point where one suppressed variant can move coverage by a full
# threshold-width. Below this, coverage is still computed and printed
# (informational), but doesn't gate; the structural gates (DROPPED, TRUNCATED,
# MISSING, EXTRA_AUDIO, NAMES, NEGATION) remain meaningful at any length and still
# decide the exit code.
MIN_COVERAGE_TOKENS = 150


# ---------------------------------------------------------------- normalization

def strip_possessive(t):
    if t.endswith("'s"):
        return t[:-2]
    if len(t) > 1 and t.endswith("'"):
        return t[:-1]
    return t


def merge_single_letters(tokens):
    out, i = [], 0
    while i < len(tokens):
        if len(tokens[i]) == 1 and tokens[i].isalpha():
            j = i
            letters = []
            while j < len(tokens) and len(tokens[j]) == 1 and tokens[j].isalpha():
                letters.append(tokens[j])
                j += 1
            out.append(''.join(letters) if len(letters) >= 2 else letters[0])
            i = j
        else:
            out.append(tokens[i])
            i += 1
    return out


def expand_negation_contractions(text):
    text = CONTRACTION_SPECIAL_RE.sub(lambda m: CONTRACTION_SPECIAL[m.group(1).lower()], text)
    text = CONTRACTION_GENERIC_RE.sub(r'\1 not', text)
    return text


def normalize(text):
    text = text.translate(CURLY)
    text = expand_negation_contractions(text)
    text = text.lower().replace('-', ' ')
    raw = re.findall(r"[a-z0-9']+", text)
    tokens = []
    for t in raw:
        t = strip_possessive(t)
        t = t.strip("'")
        if not t or any(ch.isdigit() for ch in t) or t in NUMBER_WORDS:
            continue
        tokens.append(t)
    return merge_single_letters(tokens)


# ---------------------------------------------------------------------- inputs

DIALOGUE_RE = re.compile(r'([A-Z]+):\s*(.+)')


def parse_script_lines(path):
    """Dialogue lines in file order: [{'line', 'speaker', 'text', 'tokens'}, ...]."""
    lines = []
    for n, raw in enumerate(open(path, encoding='utf-8'), 1):
        line = raw.strip()
        if not line or line.startswith('#') or line == '---':
            continue
        if re.fullmatch(r'\[pause [\d.]+\]', line):
            continue
        m = DIALOGUE_RE.fullmatch(line)
        if not m:
            continue
        speaker, text = m.group(1), m.group(2)
        lines.append({'line': n, 'speaker': speaker, 'text': text, 'tokens': normalize(text)})
    return lines


def load_ignore_file(path):
    pairs = set()
    if path and os.path.exists(path):
        for raw in open(path, encoding='utf-8'):
            line = raw.strip()
            if not line or line.startswith('#') or '~' not in line:
                continue
            exp, heard = line.split('~', 1)
            pairs.add((tuple(normalize(exp)), tuple(normalize(heard))))
    return pairs


def load_lexicon_ignore_pairs(path):
    """Each 'written => spoken' rule becomes ignore pairs covering expected=written vs
    heard in {written, spoken} (see module docstring): written heard as spoken (the
    fix worked), and written heard as written (whisper still heard the original
    letters). Both the whole-phrase pair and, when the two sides have the same word
    count, a per-word pair at each differing position -- difflib usually isolates
    just the one changed word (e.g. "X-team"/"ex team" -> only "x" vs "ex" shows up
    as a mismatch, since "team" already matches on both sides), so a phrase-level
    pair alone would rarely actually fire."""
    pairs = set()
    if path and os.path.exists(path):
        for raw in open(path, encoding='utf-8'):
            line = raw.strip()
            if not line or line.startswith('#') or '=>' not in line:
                continue
            written, spoken = line.split('=>', 1)
            w, s = tuple(normalize(written.strip())), tuple(normalize(spoken.strip()))
            if not w or not s:
                continue
            pairs.add((w, s))
            pairs.add((w, w))
            if len(w) == len(s):
                for wt, st in zip(w, s):
                    pairs.add(((wt,), (st,)))
                    pairs.add(((wt,), (wt,)))
    return pairs


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


# --------------------------------------------------------------- backend choice
#
# Two transcription backends. Backend A (whisper-cli / whisper.cpp) is tried
# first -- it's a single native binary with no Python environment of its own to
# go stale. Backend B (faster-whisper) is what the installer provisions into its
# own venv when whisper-cli isn't available; qa.py never imports it directly (that
# would make this file depend on a third-party package just to run --selftest), it
# shells out to `config.venv_python() -m <inline script>` instead.

def resolve_whisper_cli(which_config=_UNSET, which_fn=None):
    """A usable whisper-cli path, or None. Order: config.detect()['qa']['whisper_cli']
    (the installer's own idea of where it put it, or found it), then PATH. Callers
    (selftest) can inject a fake config / which() via the keyword args; production
    code passes neither, meaning "use the real module-level `config`, if importable,
    and the real shutil.which"."""
    cfg = config if which_config is _UNSET else which_config
    which_fn = which_fn or shutil.which
    if cfg:
        try:
            path = cfg.detect().get('qa', {}).get('whisper_cli')
        except Exception:
            path = None
        if path:
            return path
    return which_fn('whisper-cli')


def resolve_qa_level(which_config=_UNSET):
    """--model overrides this entirely (handled by the caller); absent that, the
    model/size level is config.load()['qa_level'], falling back to whatever
    config.detect()['qa_active'] already settled on (e.g. the best model actually
    present on disk). Returns None with no config at all.

    config.py's own DEFAULTS ship qa_level="auto" (no explicit choice) and "none"
    (explicitly no QA level); neither is a real ggml/faster-whisper size name, so
    both fall through to detect()['qa_active'] here -- which already resolves
    "none" to None on its own, so this converges to the same answer either way."""
    cfg = config if which_config is _UNSET else which_config
    if not cfg:
        return None
    try:
        level = cfg.load().get('qa_level')
    except Exception:
        level = None
    if level and level not in ('auto', 'none'):
        return level
    try:
        return cfg.detect().get('qa_active')
    except Exception:
        return None


def resolve_ggml_model(which_config=_UNSET, level_override=None):
    """<models_dir>/ggml-<level>.bin for the resolved qa level -- config owns
    *discovering* installed models (detect()['qa']['models']); this only maps a
    level name to whisper.cpp's conventional filename inside that same directory.
    `level_override` lets a caller try a specific level (e.g. --model "small",
    which isn't itself an existing path) before falling back to config's own
    qa_level/qa_active resolution."""
    cfg = config if which_config is _UNSET else which_config
    level = level_override or resolve_qa_level(which_config=cfg)
    if not level or not cfg:
        return None
    try:
        models_dir = cfg.models_dir()
    except Exception:
        return None
    path = os.path.join(models_dir, f'ggml-{level}.bin')
    return path if os.path.exists(path) else None


def faster_whisper_venv(which_config=_UNSET):
    """config.venv_python() if config.detect() reports faster-whisper actually
    importable there, else None -- a venv existing is not the same as the package
    being installed in it, so this trusts config's own probe rather than just
    checking the interpreter is present."""
    cfg = config if which_config is _UNSET else which_config
    if not cfg:
        return None
    try:
        ready = cfg.detect().get('qa', {}).get('faster_whisper')
    except Exception:
        ready = False
    if not ready:
        return None
    try:
        return cfg.venv_python()
    except Exception:
        return None


def select_backend(model_override, which_config=_UNSET, which_fn=None):
    """Returns ('whispercpp', whisper_cli_path, ggml_model_path) or
    ('faster_whisper', venv_python_path, size_level). Exits 3 if neither backend is
    usable. `model_override` (--model) is a ggml file path for backend A or a size
    level ("small") for backend B -- whichever backend actually gets picked.

    MED 5: if model_override isn't itself an existing path (e.g. --model small
    with whisper-cli installed), it's tried as a *level name* against the
    conventional ggml filename before backend A is abandoned -- otherwise a
    perfectly usable whisper-cli + <models_dir>/ggml-small.bin combination would
    be dropped for no reason other than "small" not literally being a file."""
    cfg = config if which_config is _UNSET else which_config
    whisper_cli = resolve_whisper_cli(which_config=cfg, which_fn=which_fn)
    if whisper_cli:
        model_path = None
        if model_override and os.path.exists(model_override):
            model_path = model_override
        else:
            model_path = resolve_ggml_model(which_config=cfg, level_override=model_override)
        if model_path and os.path.exists(model_path):
            return ('whispercpp', whisper_cli, model_path)
    venv_python = faster_whisper_venv(which_config=cfg)
    if venv_python:
        level = model_override or resolve_qa_level(which_config=cfg) or 'small'
        return ('faster_whisper', venv_python, level)
    die('audio QA not installed — run: /podcast upgrade qa', 3)


# The faster-whisper backend is driven through this tiny inline script rather than
# an importable helper module, so a change here can't accidentally start requiring
# faster-whisper to be importable by qa.py's own interpreter.
_FASTER_WHISPER_RUNNER = (
    "import sys\n"
    "from faster_whisper import WhisperModel\n"
    "model = WhisperModel(sys.argv[2], device='cpu', compute_type='int8')\n"
    "segments, _ = model.transcribe(sys.argv[1])\n"
    "text = ' '.join(s.text.strip() for s in segments)\n"
    "with open(sys.argv[3], 'w', encoding='utf-8') as f:\n"
    "    f.write(text)\n"
)


# MED 4: these run unattended/backgrounded by the skill (the queue worker), so a
# wedged ffmpeg or transcription backend must not hang forever. FFMPEG_TIMEOUT is
# generous for a probe/convert of a single episode-length file; TRANSCRIBE_TIMEOUT
# is generous for a long transcription on a slow/loaded machine.
FFMPEG_TIMEOUT = 60
TRANSCRIBE_TIMEOUT = 1800


def _run_with_timeout(cmd, timeout, what):
    """subprocess.run with a timeout, turned into a clean exit 2 (a tool error --
    not a hang, not a raw traceback, and distinct from exit 3 "not installed" and
    exit 1 "QA gate failed") if the process wedges."""
    try:
        return subprocess.run(cmd, check=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        die(f'{what} timed out after {timeout}s', 2)


def transcribe(audio_path, workdir, model_override=None, which_config=_UNSET, which_fn=None):
    """Selects a backend (exits 3 if none is usable), converts AUDIO to 16 kHz mono
    once, and runs whichever backend was picked."""
    backend, tool, model = select_backend(model_override, which_config=which_config, which_fn=which_fn)
    wav = os.path.join(workdir, 'audio.wav')
    _run_with_timeout(['ffmpeg', '-y', '-loglevel', 'error', '-i', audio_path,
                       '-ar', '16000', '-ac', '1', wav], FFMPEG_TIMEOUT, 'ffmpeg (convert)')
    if backend == 'whispercpp':
        out_prefix = os.path.join(workdir, 't')
        _run_with_timeout([tool, '-m', model, '-f', wav, '-t', '8', '-np',
                           '-otxt', '-of', out_prefix], TRANSCRIBE_TIMEOUT, 'whisper-cli')
        with open(out_prefix + '.txt', encoding='utf-8') as f:
            return f.read()
    # backend == 'faster_whisper': `tool` is the installer venv's python; run the
    # inline runner script as a subprocess rather than importing faster-whisper
    # into this process.
    runner_path = os.path.join(workdir, '_fw_runner.py')
    with open(runner_path, 'w', encoding='utf-8') as f:
        f.write(_FASTER_WHISPER_RUNNER)
    out_txt = os.path.join(workdir, 'fw.txt')
    _run_with_timeout([tool, runner_path, wav, model, out_txt], TRANSCRIBE_TIMEOUT, 'faster-whisper')
    with open(out_txt, encoding='utf-8') as f:
        return f.read()


def transcript_path_for(audio_path):
    """Path-aware: os.path.splitext only looks at the basename, so a dot in a
    directory component (e.g. episodes/v1.0/tone) doesn't get mistaken for the
    file's own extension."""
    return os.path.splitext(audio_path)[0] + '.transcript.txt'


def write_transcript(path, text, warn_stream=sys.stderr):
    """Save the transcript next to the audio; warn (not block) if one is already
    there with different content."""
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as f:
                old = f.read()
        except (OSError, UnicodeDecodeError):
            old = None
        if old is not None and old != text:
            print(f'warning: overwriting existing transcript {path} (content differs)',
                  file=warn_stream)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


# --------------------------------------------------------------------- analysis

def line_spans_from(lines):
    spans, pos = [], 0
    for ld in lines:
        start = pos
        pos += len(ld['tokens'])
        spans.append({'start': start, 'end': pos, 'line': ld['line'], 'speaker': ld['speaker']})
    return spans


def line_containing(idx, spans):
    for sp in spans:
        if sp['start'] <= idx < sp['end']:
            return sp
    prev = None
    for sp in spans:
        if sp['end'] <= idx:
            prev = sp
        elif sp['start'] > idx:
            break
    return prev or (spans[0] if spans else None)


def split_by_line(i1, i2, spans):
    """Yield (index-in-spans, span, clip_start, clip_end) for line spans overlapping
    [i1, i2) -- used only where the mapping is exact (matched/'equal' token counts),
    never to guess how a mismatch should be divided between lines."""
    for idx, sp in enumerate(spans):
        s, e = max(i1, sp['start']), min(i2, sp['end'])
        if s < e:
            yield idx, sp, s, e


def touched_lines(i1, i2, spans):
    return [sp['line'] for sp in spans if sp['start'] < i2 and sp['end'] > i1]


def find_proper_words(lines):
    """A word counts as a name if it is CAPITALISED SOMEWHERE THAT ISN'T just the
    first word of a line or sentence (mid-sentence capitalisation is real evidence
    of a proper noun) OR it is ALL-CAPS with length > 1 (an acronym reads as a name
    regardless of position, e.g. "ACRO" even though it only ever opens a sentence
    in this episode) -- AND it never appears in lowercase anywhere in the script.
    Sentence-initial-only capitalisation alone is NOT evidence: plain sentence
    openers ("Okay", "Employee[s]", "You'll", ...) are capitalised there by
    grammar, not because they're names, and a script's habit of never happening to
    write them lowercase elsewhere doesn't change that. Trade-off accepted: a name
    that only ever opens a sentence and is never abbreviated in caps (e.g. "Robin",
    "Vendorly" in this episode) is missed. Excludes single letters and
    I/I'm/I'd/I'll/I've (the normalized form of any of those starts with "i'",
    except bare "I" which is length 1)."""
    lower = set(t for ld in lines for w in re.findall(r"\b[a-z][a-z'’-]*", ld['text']) for t in normalize(w))
    never_lower = set(t for ld in lines for w in re.findall(r"\b[A-Z][A-Za-z'’-]*", ld['text'])
                       for t in normalize(w)) - lower

    mid_sentence_cap = set()
    for ld in lines:
        for sentence in re.split(r'(?<=[.!?])\s+', ld['text']):
            words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]*", sentence)
            for idx, w in enumerate(words):
                if idx and w[0].isupper():
                    mid_sentence_cap.update(normalize(w))
    all_caps = set(t for ld in lines for w in re.findall(r"\b[A-Z]{2,}\b", ld['text']) for t in normalize(w))

    candidate = never_lower & (mid_sentence_cap | all_caps)
    return {t for t in candidate if len(t) > 1 and not t.startswith("i'")}


def partition_leftover(exp_tokens, heard_tokens, ignore_pairs):
    """Re-align one op's own expected/heard tokens and drop any piece that is
    itself an exact ignore-pair or concat-equal match, so a larger mismatch that
    merges one known-benign word with one genuinely new one (e.g. "Okay, Zenlift"
    for "OK, Zenlyft" -- the ignore pair only covers zenlyft/zenlift) is judged on
    what's actually left, not the whole merged span.

    When both sides have the same word count, pair them positionally (word i of
    expected against word i of heard) -- difflib's LCS-based SequenceMatcher can't
    discover this alignment on its own when every word differs (no identical
    tokens for it to anchor on, e.g. "okay"/"zenlyft" vs "ok"/"zenlift" share no
    token at all), but a same-length replace is exactly the shape a word-for-word
    mishearing takes. Otherwise (a real insert/delete inside the op) fall back to a
    nested SequenceMatcher, which handles that shape correctly.

    Returns (leftover_expected, leftover_heard) tuples."""
    if len(exp_tokens) == len(heard_tokens):
        leftover_exp, leftover_heard = [], []
        for e, h in zip(exp_tokens, heard_tokens):
            if e == h or ((e,), (h,)) in ignore_pairs:
                continue
            leftover_exp.append(e)
            leftover_heard.append(h)
        return tuple(leftover_exp), tuple(leftover_heard)

    sm = difflib.SequenceMatcher(None, exp_tokens, heard_tokens, autojunk=False)
    leftover_exp, leftover_heard = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        sub_exp, sub_heard = tuple(exp_tokens[i1:i2]), tuple(heard_tokens[j1:j2])
        if tag == 'replace' and ''.join(sub_exp) == ''.join(sub_heard):
            continue
        if (sub_exp, sub_heard) in ignore_pairs:
            continue
        leftover_exp.extend(sub_exp)
        leftover_heard.extend(sub_heard)
    return tuple(leftover_exp), tuple(leftover_heard)


def line_label(op):
    if op['type'] == 'insert':
        return f"near L{op['near_line']}" if op['near_line'] is not None else 'near start'
    ls = op.get('lines') or []
    if not ls:
        return 'L?'
    if len(ls) == 1:
        return f'L{ls[0]}'
    return f'L{ls[0]}–L{ls[-1]}'


def analyze(lines, heard_text, ignore_pairs, threshold, min_coverage_tokens=MIN_COVERAGE_TOKENS):
    expected = [tok for ld in lines for tok in ld['tokens']]
    heard = normalize(heard_text)
    spans = line_spans_from(lines)
    spans_by_line = {sp['line']: sp for sp in spans}
    proper_words = find_proper_words(lines)

    sm = difflib.SequenceMatcher(None, expected, heard, autojunk=False)
    opcodes = sm.get_opcodes()

    matched = [0] * len(spans)
    ops = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'equal':
            for idx, sp, s, e in split_by_line(i1, i2, spans):
                matched[idx] += e - s
            continue

        exp_span = tuple(expected[i1:i2])
        heard_span = tuple(heard[j1:j2])

        if tag == 'insert':
            near = line_containing(i1, spans)
            op = {'type': 'insert', 'lines': [], 'near_line': near['line'] if near else None,
                  'line': near['line'] if near else None,
                  'speaker': near['speaker'] if near else None,
                  'expected': exp_span, 'heard': heard_span, 'len': j2 - j1}
        else:
            tl = touched_lines(i1, i2, spans)
            op = {'type': tag, 'lines': tl, 'near_line': None,
                  'line': tl[0] if len(tl) == 1 else None,
                  'speaker': spans_by_line[tl[0]]['speaker'] if len(tl) == 1 else None,
                  'expected': exp_span, 'heard': heard_span, 'len': i2 - i1}

        op['extra'] = len(op['heard']) - len(op['expected'])
        full_suppressed = (tag == 'replace' and ''.join(exp_span) == ''.join(heard_span)) \
            or (exp_span, heard_span) in ignore_pairs
        if full_suppressed:
            leftover_exp, leftover_heard = (), ()
        else:
            leftover_exp, leftover_heard = partition_leftover(list(exp_span), list(heard_span), ignore_pairs)
        op['leftover_expected'] = leftover_exp
        op['leftover_heard'] = leftover_heard
        op['suppressed'] = full_suppressed or (not leftover_exp and not leftover_heard)
        # How far short the (post-suppression) heard side falls of the expected
        # side -- a replace op can lose words too (six words collapsed into one
        # garbled word is a replace, not a delete; MISSING must see it).
        op['shortfall'] = len(leftover_exp) - len(leftover_heard)
        ops.append(op)

    dropped = [ld for ld, m in zip(lines, matched) if ld['tokens'] and m == 0]
    truncated = [{'line': ld['line'], 'speaker': ld['speaker'], 'matched': m, 'total': len(ld['tokens'])}
                 for ld, m in zip(lines, matched)
                 if len(ld['tokens']) >= TRUNCATED_MIN_TOKENS and 0 < m
                 and m / len(ld['tokens']) < TRUNCATED_MAX_MATCH_SHARE]

    report_lines = []
    flagged_lines = set()
    names_flags, negation_flags, extra_flags, missing_flags = [], [], [], []

    for op in ops:
        label = line_label(op)
        # Negation is judged by count, not presence: a swap that expands/contracts a
        # contraction is invisible after normalization (both sides already say "not"),
        # while adding, dropping, or replacing an actual negation word changes the
        # count on one side but not the other, in either direction.
        exp_neg = sum(t in NEGATION_WORDS for t in op['expected'])
        heard_neg = sum(t in NEGATION_WORDS for t in op['heard'])
        neg_mismatch = not op['suppressed'] and exp_neg != heard_neg
        is_missing_delete = op['type'] == 'delete' and op['len'] >= MISSING_MIN_TOKENS and not op['suppressed']
        is_missing_replace = (op['type'] == 'replace' and not op['suppressed']
                               and op['shortfall'] >= MISSING_MIN_TOKENS)
        is_missing = is_missing_delete or is_missing_replace

        if op['type'] == 'replace':
            if not op['suppressed']:
                sp = f" {op['speaker']}" if op['speaker'] else ''
                if is_missing_replace:
                    report_lines.append(f'MISSING {label}{sp}: expected {len(op["leftover_expected"])} words, '
                                         f'heard {len(op["leftover_heard"])} — expected '
                                         f'"{" ".join(op["leftover_expected"])}" heard "{" ".join(op["leftover_heard"])}"')
                    missing_flags.append({'label': label, 'lines': op['lines'], 'shortfall': op['shortfall'],
                                           'expected': op['leftover_expected'], 'heard': op['leftover_heard']})
                else:
                    report_lines.append(f'{label}{sp}: expected "{" ".join(op["leftover_expected"])}" '
                                         f'heard "{" ".join(op["leftover_heard"])}"')
                flagged_lines.update(op['lines'])
        elif op['type'] == 'delete':
            sp = f" {op['speaker']}" if op['speaker'] else ''
            if is_missing:
                report_lines.append(f'MISSING {label}{sp}: {op["len"]}-word run removed — '
                                     f'"{" ".join(op["expected"])}"')
                flagged_lines.update(op['lines'])
                missing_flags.append({'label': label, 'lines': op['lines'], 'len': op['len'],
                                       'expected': op['expected']})
            elif op['len'] >= 3 or neg_mismatch:
                report_lines.append(f'{label}{sp}: missing "{" ".join(op["expected"])}"')
                flagged_lines.update(op['lines'])
        elif op['type'] == 'insert':
            if not op['suppressed'] and (op['len'] >= 3 or neg_mismatch):
                report_lines.append(f'extra heard "{" ".join(op["heard"])}" {label}')
                if op['near_line'] is not None:
                    flagged_lines.add(op['near_line'])

        if neg_mismatch:
            words = sorted((set(t for t in op['expected'] if t in NEGATION_WORDS)
                             | set(t for t in op['heard'] if t in NEGATION_WORDS)))
            negation_flags.append({'label': label, 'lines': op['lines'], 'words': words,
                                    'expected': op['expected'], 'heard': op['heard']})
            flagged_lines.update(op['lines'])

        extra_hit = ((op['type'] == 'replace' and op['extra'] >= EXTRA_AUDIO_PER_OP)
                     or (op['type'] == 'insert' and op['len'] >= EXTRA_AUDIO_INSERT_MIN))
        if extra_hit and not op['suppressed']:
            extra_flags.append({'label': label, 'type': op['type'], 'extra': op['extra'],
                                 'heard': op['heard']})
            flagged_lines.update(op['lines'] or ([op['near_line']] if op['near_line'] is not None else []))

        if op['type'] == 'replace' and not op['suppressed']:
            names = [t for t in op['leftover_expected'] if t in proper_words]
            if names:
                names_flags.append({'label': label, 'names': names,
                                     'expected': op['leftover_expected'], 'heard': op['leftover_heard']})
                flagged_lines.update(op['lines'])

    for t in truncated:
        pct = 100 * t['matched'] / t['total']
        report_lines.append(f'L{t["line"]} {t["speaker"]}: TRUNCATED '
                             f'({t["matched"]}/{t["total"]} words matched, {pct:.0f}%)')
        flagged_lines.add(t['line'])

    for e in extra_flags:
        report_lines.append(f'EXTRA AUDIO {e["label"]}: {e["extra"]} extra heard tokens: '
                             f'"{" ".join(e["heard"])[:150]}"')

    total_heard = len(heard)
    matched_total = sum(matched)
    unmatched_heard = total_heard - matched_total
    extra_audio_global = total_heard > 0 and (unmatched_heard / total_heard) > EXTRA_AUDIO_GLOBAL_FRACTION
    if extra_audio_global:
        report_lines.append(f'EXTRA AUDIO (total): {unmatched_heard}/{total_heard} heard tokens '
                             f'unmatched ({100 * unmatched_heard / total_heard:.1f}%, threshold '
                             f'{100 * EXTRA_AUDIO_GLOBAL_FRACTION:.0f}%)')

    for nf in names_flags:
        report_lines.append(f'NAMES {nf["label"]}: expected "{" ".join(nf["expected"])}" heard '
                             f'"{" ".join(nf["heard"])}" -- round-trip the word alone, then add a '
                             f'lexicon rule (voice says it wrong) or a qa-ignore pair (whisper mishears it)')

    for ng in negation_flags:
        report_lines.append(f'NEGATION {ng["label"]}: removed {", ".join(ng["words"])} -- expected '
                             f'"{" ".join(ng["expected"])}" heard "{" ".join(ng["heard"])}"')

    for ld in dropped:
        report_lines.append(f'L{ld["line"]} {ld["speaker"]}: DROPPED (no matched words) — "{ld["text"]}"')

    total_expected = len(expected)
    coverage = matched_total / total_expected if total_expected else 1.0
    # Below min_coverage_tokens the rate is too noisy to gate on (see
    # MIN_COVERAGE_TOKENS above) -- still computed and reported, just not gated.
    coverage_gated = total_expected >= min_coverage_tokens

    gates = []
    if coverage_gated and coverage < threshold:
        gates.append('COVERAGE')
    if dropped:
        gates.append('DROPPED')
    if truncated:
        gates.append('TRUNCATED')
    if missing_flags:
        gates.append('MISSING')
    if extra_flags or extra_audio_global:
        gates.append('EXTRA_AUDIO')
    if names_flags:
        gates.append('NAMES')
    if negation_flags:
        gates.append('NEGATION')
    ok = not gates

    return {
        'coverage': coverage,
        'coverage_gated': coverage_gated,
        'min_coverage_tokens': min_coverage_tokens,
        'expected_token_count': total_expected,
        'matched_token_count': matched_total,
        'flagged_line_count': len(flagged_lines),
        'dropped_line_count': len(dropped),
        'dropped_lines': [{'line': ld['line'], 'speaker': ld['speaker'], 'text': ld['text']} for ld in dropped],
        'truncated_lines': truncated,
        'missing_flags': missing_flags,
        'extra_audio': extra_flags,
        'extra_audio_global': extra_audio_global,
        'unmatched_heard_fraction': (unmatched_heard / total_heard) if total_heard else 0.0,
        'names_flagged': names_flags,
        'negation_flagged': negation_flags,
        'ops': ops,
        'threshold': threshold,
        'gates': gates,
        'ok': ok,
        'report_lines': report_lines,
    }


# -------------------------------------------------------------------------- CLI

def build_arg_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument('script', nargs='?')
    ap.add_argument('audio', nargs='?')
    ap.add_argument('--transcript')
    ap.add_argument('--lexicon', default=None,
                     help='pronunciation rules file; default is <directory of SCRIPT>/'
                          'lexicon.txt if the episode has one, else the templates/lexicon.txt '
                          'shipped with this skill (see default_sidecar_path())')
    ap.add_argument('--ignore', default=None,
                     help='QA ignore-pairs file; default is <directory of SCRIPT>/'
                          'qa-ignore.txt if the episode has one, else the '
                          'templates/qa-ignore.txt shipped with this skill')
    ap.add_argument('--model', default=None,
                     help='ggml model path (whisper-cli backend) or size level such as '
                          '"small" (faster-whisper backend); default resolves via '
                          "config.load()['qa_level'] / detect()['qa_active']")
    ap.add_argument('--json', dest='json_out')
    ap.add_argument('--threshold', type=float, default=0.96)
    ap.add_argument('--min-coverage-tokens', type=int, default=MIN_COVERAGE_TOKENS,
                     help='the coverage/--threshold gate only applies at or above this many '
                          'normalized expected tokens (default %(default)s, ~a minute of speech) '
                          '-- below it, coverage is still computed and printed but does not gate; '
                          'see MIN_COVERAGE_TOKENS')
    ap.add_argument('--selftest', action='store_true')
    return ap


def run_selftest():
    global TEMPLATES_DIR
    ok = True

    def check(name, cond):
        nonlocal ok
        print(('PASS' if cond else 'FAIL') + f'  {name}')
        if not cond:
            ok = False

    def mklines(pairs):
        return [{'line': i + 1, 'speaker': sp, 'text': tx, 'tokens': normalize(tx)}
                for i, (sp, tx) in enumerate(pairs)]

    lines = mklines([('MAYA', 'Zenlyft reported revenue of four hundred ninety five million dollars.'),
                      ('ALEX', 'The C E O spoke about growth in twenty twenty-six.'),
                      ('MAYA', 'This line will not be spoken at all.')])

    heard = ('Zenlyft reported revenue of 495 million dollars. '
             'The CEO spoke about growth in 2026. '
             'This line will not be spoken at all.')
    r = analyze(lines, heard, set(), 0.93)
    check('exact match (numbers/CEO normalized away) -> coverage 1.0', abs(r['coverage'] - 1.0) < 1e-9)
    check('exact match -> ok', r['ok'] is True)
    check('"twenty twenty-six" vs "2026" not flagged', not any('2026' in ''.join(o['heard']) for o in r['ops']
          if o['type'] == 'replace' and not o['suppressed']))
    check('"C E O" vs "CEO" not flagged',
          not any(o['type'] == 'replace' and 'ceo' in o['expected'] for o in r['ops'] if not o['suppressed']))

    heard2 = ('Trendly reported revenue of 495 million dollars. '
              'The CEO spoke about growth in 2026. '
              'This line will not be spoken at all.')
    r2 = analyze(lines, heard2, set(), 0.93)
    sub_ops = [o for o in r2['ops'] if o['type'] == 'replace' and not o['suppressed']]
    check('substitution detected', len(sub_ops) >= 1)
    check('substitution flagged on line 1', any(o.get('line') == 1 for o in sub_ops))
    check('substitution content is zenlyft/trendly',
          any('zenlyft' in o['expected'] and 'trendly' in o['heard'] for o in sub_ops))
    check('coverage below 1.0 after a substitution', r2['coverage'] < 1.0)

    ignore = {(('zenlyft',), ('trendly',))}
    r3 = analyze(lines, heard2, ignore, 0.93)
    check('ignore pair suppresses the report line',
          not any(o['type'] == 'replace' and not o['suppressed']
                  and 'zenlyft' in o['expected'] for o in r3['ops']))
    check('suppressed op still recorded (for --json)',
          any(o['suppressed'] and 'zenlyft' in o['expected'] for o in r3['ops']))

    heard3 = 'Zenlyft reported revenue of 495 million dollars. The CEO spoke about growth in 2026.'
    r4 = analyze(lines, heard3, set(), 0.93)
    check('dropped line detected', r4['dropped_line_count'] == 1)
    check('dropped line is line 3', r4['dropped_lines'][0]['line'] == 3)
    check('dropped line fails the gate (ok False)', r4['ok'] is False)
    check('dropped line fails via DROPPED gate', 'DROPPED' in r4['gates'])

    with tempfile.TemporaryDirectory() as td:
        lex_path = os.path.join(td, 'lexicon.txt')
        with open(lex_path, 'w', encoding='utf-8') as f:
            f.write('X-team => ex team\n')
        pairs = load_lexicon_ignore_pairs(lex_path)
        check('lexicon rule becomes written->spoken ignore pair',
              (('x', 'team'), ('ex', 'team')) in pairs)
        check('lexicon rule also becomes written->written ignore pair (whisper still hears the letters)',
              (('x', 'team'), ('x', 'team')) in pairs)
        check('lexicon rule also becomes a per-word pair (difflib usually isolates just "x"/"ex")',
              (('x',), ('ex',)) in pairs)
        r_lex = analyze(mklines([('MAYA', 'He was on the X-team at Globex for years.')]),
                         'He was on the ex team at Globex for years.', pairs, 0.93)
        check('the per-word pair actually suppresses the report on a realistic sentence',
              not any(rl.startswith('L') for rl in r_lex['report_lines']))

    # --- possessive stripping before letter-merge
    check('"C E O\'s" normalizes to "ceo"', normalize("the C E O's resume") == ['the', 'ceo', 'resume'])
    check('"Zenlyft\'s" normalizes to "zenlyft"', normalize("Zenlyft's app") == ['zenlyft', 'app'])
    check('plural possessive: "teams\'" normalizes to "teams"', normalize("the teams' offices") == ['the', 'teams', 'offices'])
    check('negation word survives normalization untouched', normalize("do not go") == ['do', 'not', 'go'])

    # --- contraction expansion: n't -> " not" on both regular and irregular stems,
    # so a transcript that expands/contracts a negation reads identically to the script.
    check('"don\'t" expands like "do not"', normalize("don't") == normalize("do not"))
    check('"isn\'t" expands like "is not"', normalize("isn't") == normalize("is not"))
    check('"doesn\'t" expands like "does not"', normalize("doesn't") == normalize("does not"))
    check('"aren\'t" expands like "are not"', normalize("aren't") == normalize("are not"))
    check('"couldn\'t" expands like "could not"', normalize("couldn't") == normalize("could not"))
    check('"can\'t" (irregular stem) expands to "can not", not "ca not"', normalize("can't") == ['can', 'not'])
    check('"won\'t" (irregular stem) expands to "will not"', normalize("won't") == ['will', 'not'])
    check('"shan\'t" (irregular stem) expands to "shall not"', normalize("shan't") == ['shall', 'not'])
    check('"ain\'t" expands to "is not"', normalize("ain't") == ['is', 'not'])

    # --- TRUNCATED gate: a long line mostly missing
    lines_t = mklines([('MAYA', 'alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima')])
    heard_t = 'alpha bravo charlie'  # 3 of 12 tokens -> 25% matched
    rt = analyze(lines_t, heard_t, set(), 0.93)
    check('TRUNCATED gate fires on a long, mostly-missing line', 'TRUNCATED' in rt['gates'])
    check('TRUNCATED line recorded with the right counts',
          any(t['line'] == 1 and t['matched'] == 3 and t['total'] == 12 for t in rt['truncated_lines']))
    lines_t2 = mklines([('MAYA', 'alpha bravo charlie delta echo')])  # <8 tokens: DROPPED/coverage only, not TRUNCATED
    rt2 = analyze(lines_t2, 'alpha bravo', set(), 0.93)
    check('short line (<8 tokens) does not trigger TRUNCATED', 'TRUNCATED' not in rt2['gates'])

    # --- EXTRA_AUDIO gate: per-op (repeat/hallucination/wrong-line audio) and global
    lines_e = mklines([('MAYA', 'we start the show today')])
    heard_e = 'we start the show today ' + ' '.join(['blah'] * 15)
    re_ = analyze(lines_e, heard_e, set(), 0.93)
    check('EXTRA_AUDIO gate fires when heard exceeds expected by >=12 tokens', 'EXTRA_AUDIO' in re_['gates'])
    check('extra_audio op recorded', len(re_['extra_audio']) >= 1)
    lines_e2 = mklines([('MAYA', ' '.join(['word'] * 40))])
    heard_e2 = ' '.join(['word'] * 40) + ' ' + ' '.join(['noise'] * 3)  # 3/43 ~= 7% unmatched
    re2 = analyze(lines_e2, heard_e2, set(), 0.93)
    check('EXTRA_AUDIO global gate fires when >5% of heard tokens are unmatched', 'EXTRA_AUDIO' in re2['gates'])

    # --- NAMES gate v2: (mid-sentence-cap OR all-caps) AND never lowercase.
    # A word capitalised mid-sentence at least once is a name, even if it also
    # opens sentences elsewhere.
    lines_n = mklines([('ALEX', 'Sirius says the results are promising, but Sirius is cautious.'),
                        ('MAYA', 'Sirius published a new report.')])
    rn = analyze(lines_n, 'Cirrus says the results are promising, but Sirius is cautious. '
                          'Sirius published a new report.', set(), 0.93)
    check('NAMES fires on a word capitalised mid-sentence at least once', 'NAMES' in rn['gates'])
    rn_ign = analyze(lines_n, 'Cirrus says the results are promising, but Sirius is cautious. '
                              'Sirius published a new report.', {(('sirius',), ('cirrus',))}, 0.93)
    check('an ignored name mismatch does not trigger NAMES', 'NAMES' not in rn_ign['gates'])

    # An ALL-CAPS acronym is a name regardless of position (the ACRO bug: it only
    # ever opens a sentence in the real episode, but is still a name).
    lines_acr = mklines([('ALEX', 'ACRO ran a randomized trial.'), ('MAYA', 'ACRO published its findings.')])
    racr = analyze(lines_acr, 'Arrow ran a randomized trial. ACRO published its findings.', set(), 0.93)
    check('an ALL-CAPS acronym is a name even sentence-initial-only (ACRO)', 'NAMES' in racr['gates'])

    # Accepted trade-off: a name that only ever opens a sentence, and is never
    # written in all-caps, is missed (matches Robin/Vendorly in the real episode).
    lines_j = mklines([('MAYA', 'Robin is the CTO.'), ('ALEX', 'Robin joined in twenty twenty-five.')])
    rj = analyze(lines_j, 'Robyn is the CTO. Robin joined in twenty twenty-five.', set(), 0.93)
    check('accepted trade-off: a sentence-initial-only, non-all-caps name is NOT flagged',
          'NAMES' not in rj['gates'])

    # The round-3 false positives this fix targets: plain sentence-openers are not
    # names just because the script happens to never write them lowercase elsewhere.
    lines_ok = mklines([('MAYA', "Okay, let's start."), ('ALEX', 'Employee morale matters a lot.')])
    rok = analyze(lines_ok, "OK, let's start. Employees morale matters a lot.", set(), 0.93)
    check('"Okay"->"OK" does not trigger NAMES (sentence-opener only)', 'NAMES' not in rok['gates'])
    check('"Employee"->"Employees" does not trigger NAMES (sentence-opener only)', 'NAMES' not in rok['gates'])

    # A word capitalised at sentence-start but that ALSO appears lowercase elsewhere
    # in the script is not a name.
    lines_n2 = mklines([('MAYA', 'So this matters a lot.'), ('ALEX', 'We can measure it, so it counts.')])
    proper2 = find_proper_words(lines_n2)
    check('a word capitalised only by sentence position, but also seen lowercase, is not a name',
          'so' not in proper2)

    # Common words that are always lowercase in the script never pollute NAMES, even
    # when they're the mismatched word themselves.
    lines_n3 = mklines([('MAYA', "It's a paid membership, and our engineering team ships fast.")])
    rn3 = analyze(lines_n3, "It's the paid membership, and our engineering teams ships fast.", set(), 0.93)
    check('"a"->"the" and "team"->"teams" do not trigger NAMES (both always lowercase in the script)',
          'NAMES' not in rn3['gates'])
    lines_n4 = mklines([('ALEX', "And I'm Alex.")])
    rn4 = analyze(lines_n4, "And I am Alex.", set(), 0.93)
    check('"I\'m" -> "I am" does not trigger NAMES (I-contractions excluded)', 'NAMES' not in rn4['gates'])

    # --- ignore pairs apply word-by-word inside a larger replace op. "okay" also
    # appears lowercase on the second line so it (correctly) isn't itself a NAMES
    # candidate -- isolating this check to the ignore-pair partial-suppression fix.
    lines_ig = mklines([('MAYA', "Okay, Zenlyft's app is solid."), ('ALEX', "That's okay by me.")])
    rig = analyze(lines_ig, "OK, Zenlift's app is solid. That's okay by me.",
                  {(('zenlyft',), ('zenlift',))}, 0.93)
    check('the known-noise half ("zenlyft"/"zenlift") is fully suppressed at the sub-word level',
          not any('zenlift' in nf['expected'] or 'zenlift' in nf['heard'] for nf in rig['names_flagged']))
    check('the known-noise half does not appear in the leftover report',
          not any('zenlift' in rl for rl in rig['report_lines']))
    check('NAMES does not fire from the merged op (only the benign "okay"/"ok" leftover remains)',
          'NAMES' not in rig['gates'])

    # --- NEGATION gate: count-based, not presence-based; fires in either direction,
    # even a 1-token change, but NOT on a contraction expand/contract (same count).
    lines_g = mklines([('MAYA', 'This is not a good idea.')])
    rg = analyze(lines_g, 'This is a good idea.', set(), 0.93)
    check('NEGATION gate fires when a negation word is removed (1 token)', 'NEGATION' in rg['gates'])
    check('NEGATION reported even though the delete is under the 3-token report threshold',
          any('NEGATION' in rl for rl in rg['report_lines']))
    lines_g2 = mklines([('MAYA', 'That number is real.')])
    rg2 = analyze(lines_g2, "That number isn't real.", set(), 0.93)
    check('adding "isn\'t" (net new negation, script had none) fires NEGATION', 'NEGATION' in rg2['gates'])
    lines_g3 = mklines([('MAYA', "That claim isn't a foreign idea.")])
    rg3 = analyze(lines_g3, "That claim is a foreign idea.", set(), 0.93)
    check('removing "isn\'t" fires NEGATION', 'NEGATION' in rg3['gates'])
    lines_g4 = mklines([('MAYA', "They aren't the ones winning.")])
    rg4 = analyze(lines_g4, "They are the ones winning.", set(), 0.93)
    check('removing "aren\'t" fires NEGATION', 'NEGATION' in rg4['gates'])
    lines_g5 = mklines([('MAYA', "With no explanation nor appeal.")])
    rg5 = analyze(lines_g5, "With no explanation or appeal.", set(), 0.93)
    check('removing "nor" fires NEGATION', 'NEGATION' in rg5['gates'])
    lines_g6 = mklines([('MAYA', "Don't quote the net income.")])
    rg6 = analyze(lines_g6, "Do quote the net income.", set(), 0.93)
    check('"don\'t" -> "do" (losing the negation, not just the contraction) fires NEGATION',
          'NEGATION' in rg6['gates'])
    rg7 = analyze(lines_g, "This is not a good idea.", set(), 0.93)
    check('exact match with "not" present on both sides does not fire NEGATION', 'NEGATION' not in rg7['gates'])
    lines_g8 = mklines([('MAYA', "You don't need to raise it.")])
    rg8 = analyze(lines_g8, "You do not need to raise it.", set(), 0.93)
    check('"don\'t" heard as "do not" (pure contraction swap) does not fire NEGATION',
          'NEGATION' not in rg8['gates'])

    # --- MISSING gate: an unsuppressed delete run of >=4 words
    lines_ms = mklines([('MAYA', 'alpha bravo charlie delta echo foxtrot golf hotel india juliet')])
    rms = analyze(lines_ms, 'alpha bravo charlie delta india juliet', set(), 0.93)
    check('MISSING fires on a delete run of exactly 4 words', 'MISSING' in rms['gates'])
    rms2 = analyze(lines_ms, 'alpha bravo charlie delta echo foxtrot juliet', set(), 0.93)
    check('a 3-word delete run does not fire MISSING', 'MISSING' not in rms2['gates'])
    check('a 3-word delete run is still informational in the report',
          any('missing' in rl for rl in rms2['report_lines']))

    # --- MISSING also applies to REPLACE ops: a garbled stretch that whisper hears
    # as one (wrong) word is a replace, not a delete, and was invisible before.
    lines_gb = mklines([('MAYA', 'alpha bravo charlie delta echo foxtrot golf hotel india juliet')])
    rgb = analyze(lines_gb, 'alpha bravo charlie mm india juliet', set(), 0.93)  # 6 words -> "mm"
    check('MISSING fires on a replace whose expected side exceeds heard by >=4 words (6-in-1-out)',
          'MISSING' in rgb['gates'])
    check('the MISSING-replace report line is labelled MISSING',
          any(rl.startswith('MISSING ') for rl in rgb['report_lines']))
    rgb2 = analyze(lines_gb, 'alpha bravo charlie mm hotel india juliet', set(), 0.93)  # only 3 words -> "mm"
    check('a replace shortfall of only 3 words does not fire MISSING', 'MISSING' not in rgb2['gates'])

    # --- default --threshold is now 0.96 (five real decodes scored 0.980-0.985;
    # scattered small losses of ~55s landed at 0.930 and no longer pass)
    check('default --threshold is 0.96', build_arg_parser().parse_args([]).threshold == 0.96)
    import itertools
    # 100 DISTINCT alphabetic tokens -- a repeating vocabulary (NATO-style, cycled)
    # gives difflib's LCS matcher too many equally-good alignments to choose from
    # and it picks one that doesn't correspond to "drop these 7 positions" at all.
    words100 = [''.join(t) for t in itertools.islice(itertools.product('abcdefghij', repeat=3), 100)]
    lines_cov = mklines([('MAYA', ' '.join(words100))])
    drop = {10, 22, 34, 46, 58, 70, 82}  # 7 scattered single-word drops (no run >=4, so MISSING stays clear)
    heard_93pct = ' '.join(w for i, w in enumerate(words100) if i not in drop)
    # This is a 100-token script -- below the default MIN_COVERAGE_TOKENS=150, so
    # the coverage gate wouldn't apply at all with the real default (that's the
    # separate short-script behavior tested below). min_coverage_tokens=0 isolates
    # the coverage/threshold arithmetic itself, which is what this repro is for.
    r_93_old = analyze(lines_cov, heard_93pct, set(), 0.93, min_coverage_tokens=0)
    r_93_new = analyze(lines_cov, heard_93pct, set(), 0.96, min_coverage_tokens=0)
    check('the scattered-drop repro is exactly 0.930 coverage', abs(r_93_old['coverage'] - 0.93) < 1e-9)
    check('0.930 coverage passed the old 0.93 threshold', r_93_old['ok'] is True)
    check('the same 0.930 coverage now fails the 0.96 default threshold', r_93_new['ok'] is False)
    check('...specifically via the COVERAGE gate (not MISSING -- each drop is isolated)',
          r_93_new['gates'] == ['COVERAGE'])

    check('--min-coverage-tokens defaults to MIN_COVERAGE_TOKENS (150)',
          build_arg_parser().parse_args([]).min_coverage_tokens == MIN_COVERAGE_TOKENS)

    # --- MIN_COVERAGE_TOKENS: the real bug this closes. A 21-token smoke-test-sized
    # script that suppresses one benign compound-word variant ("plugin"/"plugins",
    # the same class as the real "plugin"/"plug-in" transcription variant) loses
    # ~4.8% of its tokens on that account alone -- below the default threshold, but
    # below MIN_COVERAGE_TOKENS too, so it must NOT gate (the identical script
    # would score 1.0 on a clean re-render; the loss is sampling noise, not a
    # defect). 21 tokens (not 20) and this exact wording are deliberate: at 20 the
    # single unmatched heard token sits at precisely 5.0% of heard tokens, which
    # would (correctly, and irrelevantly to this test) also trip the separate
    # EXTRA_AUDIO global-fraction gate -- 21 isolates the coverage behavior alone.
    short_text = ('Make sure the plugin loads before you open the editor and check the '
                  'console for any errors before you ship it out.')
    short_lines = mklines([('MAYA', short_text)])
    check('the short-script repro is under MIN_COVERAGE_TOKENS', len(short_lines[0]['tokens']) < MIN_COVERAGE_TOKENS)
    short_heard = short_text.replace('plugin', 'plugins')
    plugin_ignore = {(('plugin',), ('plugins',))}
    r_short = analyze(short_lines, short_heard, plugin_ignore, 0.96)
    check('a short script with one suppressed variant is below the default --threshold',
          r_short['coverage'] < 0.96)
    check('...but is NOT coverage-gated (under MIN_COVERAGE_TOKENS)', r_short['coverage_gated'] is False)
    check('...so it exits ok (0), not 1', r_short['ok'] is True and r_short['gates'] == [])

    # The same short script, but with a genuinely dropped line (a structural
    # defect, not a sample-size artifact) must still fail -- DROPPED/MISSING/etc.
    # are never conditional on script length.
    short_lines_dropped = mklines([('MAYA', short_text), ('ALEX', 'That part of the flow is brand new.')])
    r_short_dropped = analyze(short_lines_dropped, short_heard, plugin_ignore, 0.96)  # ALEX's line never heard
    check('a short script with a dropped line still fails even though it is not coverage-gated',
          r_short_dropped['coverage_gated'] is False and r_short_dropped['ok'] is False)
    check('...via the DROPPED gate', 'DROPPED' in r_short_dropped['gates'])

    # A long (>=MIN_COVERAGE_TOKENS) script with the same kind of scattered loss
    # must still gate on coverage exactly as before -- this is the "must not
    # weaken real episodes" half of the fix.
    words200 = [''.join(t) for t in itertools.islice(itertools.product('abcdefghij', repeat=3), 200)]
    lines200 = mklines([('MAYA', ' '.join(words200))])
    check('the long-script repro is at/above MIN_COVERAGE_TOKENS', len(lines200[0]['tokens']) >= MIN_COVERAGE_TOKENS)
    drop200 = set(range(10, 200, 12))  # 16 isolated single-word drops, 8% loss, no run >=4
    heard200 = ' '.join(w for i, w in enumerate(words200) if i not in drop200)
    r_long = analyze(lines200, heard200, set(), 0.96)
    check('a long script below --threshold is coverage-gated', r_long['coverage_gated'] is True)
    check('...and fails via COVERAGE, same as before this fix', r_long['ok'] is False and r_long['gates'] == ['COVERAGE'])

    # --- EXTRA_AUDIO gate: an insert run of >=6 words (repeats), lower than the
    # >=12 replace-overflow threshold, so short repeated phrases are still caught.
    # A long, distinct-word carrier line keeps the insert well under the separate
    # 5%-of-total-heard global gate, isolating the per-op threshold being tested.
    nato = ['alpha', 'bravo', 'charlie', 'delta', 'echo', 'foxtrot', 'golf', 'hotel',
            'india', 'juliet', 'kilo', 'lima', 'mike', 'november', 'oscar', 'papa',
            'quebec', 'romeo', 'sierra', 'tango', 'uniform', 'victor', 'whiskey', 'yankee', 'zulu']
    base_words = (nato * 6)[:150]
    lines_ex = mklines([('MAYA', ' '.join(base_words))])

    def with_insert(n):
        return ' '.join(base_words[:75] + [f'filler{c}' for c in 'abcdef'[:n]] + base_words[75:])
    rex = analyze(lines_ex, with_insert(6), set(), 0.93)
    check('EXTRA_AUDIO fires on a 6-word insert run (isolated from the global-fraction gate)',
          'EXTRA_AUDIO' in rex['gates'])
    rex2 = analyze(lines_ex, with_insert(5), set(), 0.93)
    check('a 5-word insert run does not fire EXTRA_AUDIO (isolated from the global-fraction gate)',
          'EXTRA_AUDIO' not in rex2['gates'])

    # --- coverage stays exact-match only: suppression must not inflate it
    lines_c = mklines([('MAYA', 'App Store users love the appstore.')])
    rc_nosupp = analyze(lines_c, 'App Store users love the app store.', set(), 0.93)
    rc_supp = analyze(lines_c, 'App Store users love the app store.', set(), 0.93)
    check('concat-equal suppression does not change coverage vs the unsuppressed run',
          rc_nosupp['coverage'] == rc_supp['coverage'])
    check('concat-equal ("appstore" vs "app store") is suppressed from the report',
          not any('appstore' in rl or 'app store' in rl for rl in rc_supp['report_lines']
                  if rl.startswith('L')))

    # --- multi-line op reporting: a range, not a guessed single line
    lines_m = mklines([('MAYA', 'alpha bravo charlie delta echo foxtrot golf hotel'),
                        ('ALEX', 'india juliet kilo lima mike november oscar papa')])
    heard_m = 'alpha bravo zulu zulu zulu zulu zulu zulu zulu zulu zulu zulu zulu zulu papa'
    rm = analyze(lines_m, heard_m, set(), 0.93)
    check('a mismatch spanning two script lines is reported as a line range',
          any('L1–L2' in rl for rl in rm['report_lines']))

    # --- robustness helpers
    check('transcript_path_for is basename-only (dot in a directory is not an extension)',
          transcript_path_for('/x/episodes/v1.0/tone') == '/x/episodes/v1.0/tone.transcript.txt')
    with tempfile.TemporaryDirectory() as td:
        import io, contextlib
        p = os.path.join(td, 'out.transcript.txt')
        with open(p, 'w', encoding='utf-8') as f:
            f.write('old content')
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            write_transcript(p, 'new content', warn_stream=buf)
        check('overwriting a differing transcript prints a warning', 'warning' in buf.getvalue().lower())
        check('overwriting a differing transcript still writes the new content',
              open(p, encoding='utf-8').read() == 'new content')
        buf2 = io.StringIO()
        p2 = os.path.join(td, 'out2.transcript.txt')
        with open(p2, 'w', encoding='utf-8') as f:
            f.write('same')
        with contextlib.redirect_stderr(buf2):
            write_transcript(p2, 'same', warn_stream=buf2)
        check('no warning when the existing transcript is identical', buf2.getvalue() == '')

    # --- no-dialogue-lines / swapped-args guard, via the real CLI
    with tempfile.TemporaryDirectory() as td:
        notes = os.path.join(td, 'notes.md')
        with open(notes, 'w', encoding='utf-8') as f:
            f.write('# Notes\nJust prose, no ALLCAPS: speaker lines here.\n')
        empty_tr = os.path.join(td, 'empty.txt')
        open(empty_tr, 'w', encoding='utf-8').write('')
        r = subprocess.run([sys.executable, __file__, notes, '/dev/null', '--transcript', empty_tr],
                            capture_output=True, text=True)
        check('a script with no dialogue lines exits 2', r.returncode == 2)

        binary_transcript = os.path.join(td, 'bin.dat')
        with open(binary_transcript, 'wb') as f:
            f.write(bytes(range(256)))
        real_script = os.path.join(td, 'script.txt')
        open(real_script, 'w', encoding='utf-8').write('MAYA: Hello there.\n')
        r2 = subprocess.run([sys.executable, __file__, real_script, '/dev/null', '--transcript', binary_transcript],
                             capture_output=True, text=True)
        check('an undecodable transcript file exits 2', r2.returncode == 2)

        r3 = subprocess.run([sys.executable, __file__, real_script, '/dev/null', '--transcript', empty_tr,
                              '--json', os.path.join(td, 'nosuchdir', 'out.json')],
                             capture_output=True, text=True)
        check('a --json path in a missing directory exits 2', r3.returncode == 2)

    # --- backend selection: whisper-cli (A) first, faster-whisper (B) fallback,
    # exit 3 when neither is usable. Fake config/which() objects keep this
    # deterministic regardless of what's actually installed on the machine running
    # --selftest -- a real host with whisper-cli on PATH must still see the same
    # PASS/FAIL here as one with nothing installed.
    class FakeQAConfig:
        def __init__(self, detect=None, load=None, venv=None,
                     raise_detect=False, raise_load=False, raise_venv=False):
            self._detect, self._load, self._venv = detect or {}, load or {}, venv
            self._raise_detect, self._raise_load, self._raise_venv = raise_detect, raise_load, raise_venv

        def detect(self):
            if self._raise_detect:
                raise RuntimeError('boom')
            return self._detect

        def load(self):
            if self._raise_load:
                raise RuntimeError('boom')
            return self._load

        def venv_python(self):
            if self._raise_venv:
                raise RuntimeError('boom')
            return self._venv

    no_which = lambda name: None
    fake_which = lambda name: '/opt/fake/whisper-cli' if name == 'whisper-cli' else None

    check('resolve_whisper_cli: config-reported path wins over PATH',
          resolve_whisper_cli(which_config=FakeQAConfig({'qa': {'whisper_cli': '/cfg/whisper-cli'}}),
                               which_fn=fake_which) == '/cfg/whisper-cli')
    check('resolve_whisper_cli: falls back to PATH when config has nothing',
          resolve_whisper_cli(which_config=FakeQAConfig(), which_fn=fake_which) == '/opt/fake/whisper-cli')
    check('resolve_whisper_cli: None when config is absent and PATH has nothing',
          resolve_whisper_cli(which_config=None, which_fn=no_which) is None)

    check('resolve_qa_level: config.load()[qa_level] wins over detect()[qa_active]',
          resolve_qa_level(FakeQAConfig(load={'qa_level': 'medium'}, detect={'qa_active': 'small'})) == 'medium')
    check('resolve_qa_level: falls back to detect() when qa_level is unset',
          resolve_qa_level(FakeQAConfig(load={}, detect={'qa_active': 'base'})) == 'base')
    check('resolve_qa_level: None with no config', resolve_qa_level(None) is None)
    check('qa_level="auto" (config.py\'s own DEFAULTS sentinel) falls through to detect(), '
          'is not treated as a literal size level',
          resolve_qa_level(FakeQAConfig(load={'qa_level': 'auto'}, detect={'qa_active': 'medium'})) == 'medium')
    check('qa_level="none" also falls through to detect() rather than being returned literally',
          resolve_qa_level(FakeQAConfig(load={'qa_level': 'none'}, detect={'qa_active': 'small'})) == 'small')

    with tempfile.TemporaryDirectory() as models_td:
        open(os.path.join(models_td, 'ggml-small.bin'), 'w', encoding='utf-8').write('x')

        class ModelsDirConfig(FakeQAConfig):
            def models_dir(self):
                return models_td

        cfg_a = ModelsDirConfig(detect={'qa': {'whisper_cli': '/cfg/whisper-cli'}}, load={'qa_level': 'small'})
        backend, tool, model = select_backend(None, which_config=cfg_a, which_fn=no_which)
        check('select_backend: whisper-cli + resolvable ggml model -> backend A',
              (backend, tool, model) == ('whispercpp', '/cfg/whisper-cli', os.path.join(models_td, 'ggml-small.bin')))

        # MED 5: --model "small" (not itself an existing path) with whisper-cli
        # installed must still resolve to <models_dir>/ggml-small.bin rather than
        # being abandoned as "not a path" and falling through past a working backend.
        cfg_level_override = ModelsDirConfig(detect={'qa': {'whisper_cli': '/cfg/whisper-cli'}})
        backend, tool, model = select_backend('small', which_config=cfg_level_override, which_fn=no_which)
        check('select_backend: --model LEVEL (not a path) still resolves against '
              'whisper-cli + <models_dir>/ggml-LEVEL.bin instead of abandoning backend A',
              (backend, tool, model) == ('whispercpp', '/cfg/whisper-cli', os.path.join(models_td, 'ggml-small.bin')))
        # ...but a level with no matching ggml file still correctly falls through
        # (to backend B if usable, else exit 3) rather than fabricating a path.
        check('resolve_ggml_model: a level_override with no matching ggml file resolves to None',
              resolve_ggml_model(which_config=cfg_level_override, level_override='medium') is None)

        # whisper-cli is on PATH, but the resolved ggml file doesn't exist -- backend A
        # is not usable, so this must NOT silently render with a missing model.
        cfg_b = ModelsDirConfig(detect={'qa': {'whisper_cli': '/cfg/whisper-cli'},
                                         'qa_active': 'medium'})  # ggml-medium.bin absent
        try:
            select_backend(None, which_config=cfg_b, which_fn=no_which)
            check('select_backend: whisper-cli present but model file missing does not silently pass', False)
        except SystemExit as e:
            check('select_backend: whisper-cli present but model file missing does not silently pass', True)
            check('...falls through to exit 3, not a crash or a bad path', e.code == 3)

    check('faster_whisper_venv: None unless config.detect()[qa][faster_whisper] is true',
          faster_whisper_venv(FakeQAConfig(detect={'qa': {'faster_whisper': False}}, venv='/state/venv/bin/python')) is None)
    check('faster_whisper_venv: returns venv_python() when faster_whisper is ready',
          faster_whisper_venv(FakeQAConfig(detect={'qa': {'faster_whisper': True}}, venv='/state/venv/bin/python'))
          == '/state/venv/bin/python')

    cfg_fw = FakeQAConfig(detect={'qa': {'faster_whisper': True}}, load={'qa_level': 'small'},
                           venv='/state/venv/bin/python')
    check('select_backend: no whisper-cli anywhere -> falls back to faster-whisper',
          select_backend(None, which_config=cfg_fw, which_fn=no_which)
          == ('faster_whisper', '/state/venv/bin/python', 'small'))
    check('select_backend: --model overrides the resolved level for backend B too',
          select_backend('base', which_config=cfg_fw, which_fn=no_which)
          == ('faster_whisper', '/state/venv/bin/python', 'base'))

    try:
        select_backend(None, which_config=FakeQAConfig(), which_fn=no_which)
        check('select_backend: neither backend usable -> exits', False)
    except SystemExit as e:
        check('select_backend: neither backend usable -> exits', True)
        check('...with exit code 3 (distinct from a QA gate failure or a tool error)', e.code == 3)
    try:
        select_backend(None, which_config=None, which_fn=no_which)
        check('select_backend: no config module at all (bare checkout) still exits cleanly', False)
    except SystemExit as e:
        check('select_backend: no config module at all (bare checkout) still exits cleanly', True)
        check('...with exit code 3', e.code == 3)
    try:
        select_backend(None, which_config=FakeQAConfig(raise_detect=True, raise_load=True), which_fn=no_which)
        check('select_backend: a config that raises everywhere still degrades to exit 3', False)
    except SystemExit as e:
        check('select_backend: a config that raises everywhere still degrades to exit 3', True)
        check('...with exit code 3', e.code == 3)

    # MED 4: a wedged subprocess must not hang forever -- it becomes a clean exit 2
    # (a tool error, distinct from gate-fail 1 and not-installed 3), not a hang.
    try:
        _run_with_timeout(['sleep', '5'], 0.2, 'test-sleep')
        check('_run_with_timeout converts a wedged subprocess into a clean exit', False)
    except SystemExit as e:
        check('_run_with_timeout converts a wedged subprocess into a clean exit', True)
        check('...with exit code 2 (a tool error, distinct from gate-fail 1 and not-installed 3)',
              e.code == 2)
    check('_run_with_timeout returns normally (no exception) for a process that finishes in time',
          _run_with_timeout(['true'], 5, 'test-true').returncode == 0)

    # HIGH 3: default_sidecar_path prefers the episode's own lexicon.txt/qa-ignore.txt,
    # falls back to the skill's templates/ copy, and --help documents where it looks.
    # Before this fix both defaulted to REPO_ROOT itself, where neither file has ever
    # lived -- the pronunciation loop was dead and QA produced at least one false
    # NAMES failure on a real episode for lack of the episode's own ignore pairs.
    with tempfile.TemporaryDirectory() as sc_td:
        ep_dir = os.path.join(sc_td, 'episode-with-lexicon')
        os.makedirs(ep_dir)
        own_lexicon = os.path.join(ep_dir, 'lexicon.txt')
        with open(own_lexicon, 'w', encoding='utf-8') as f:
            f.write('X-team => ex team\n')
        ep_script = os.path.join(ep_dir, 'script.txt')
        with open(ep_script, 'w', encoding='utf-8') as f:
            f.write('MAYA: hi\n')
        check("default_sidecar_path prefers the episode's own lexicon.txt",
              default_sidecar_path(ep_script, 'lexicon.txt') == own_lexicon)

        bare_dir = os.path.join(sc_td, 'episode-without-lexicon')
        os.makedirs(bare_dir)
        bare_script = os.path.join(bare_dir, 'script.txt')
        with open(bare_script, 'w', encoding='utf-8') as f:
            f.write('MAYA: hi\n')
        expected_lexicon_template = os.path.join(TEMPLATES_DIR, 'lexicon.txt')
        check('default_sidecar_path falls back to the skill templates/lexicon.txt '
              'when the episode has none',
              os.path.exists(expected_lexicon_template)
              and default_sidecar_path(bare_script, 'lexicon.txt') == expected_lexicon_template)
        expected_ignore_template = os.path.join(TEMPLATES_DIR, 'qa-ignore.txt')
        check('default_sidecar_path falls back to templates/qa-ignore.txt too (not just lexicon.txt)',
              os.path.exists(expected_ignore_template)
              and default_sidecar_path(bare_script, 'qa-ignore.txt') == expected_ignore_template)

        orig_templates_dir = TEMPLATES_DIR
        TEMPLATES_DIR = os.path.join(sc_td, 'no-such-templates-dir')
        check('default_sidecar_path with neither an episode nor a template copy still '
              "returns the episode path (the loaders' existing silent no-op handles it)",
              default_sidecar_path(bare_script, 'lexicon.txt') == os.path.join(bare_dir, 'lexicon.txt'))
        TEMPLATES_DIR = orig_templates_dir

    check('--lexicon --help documents the default lookup order',
          'templates/lexicon.txt' in build_arg_parser().format_help())
    check('--ignore --help documents the default lookup order',
          'templates/qa-ignore.txt' in build_arg_parser().format_help())

    return 0 if ok else 1


def main():
    ap = build_arg_parser()
    args = ap.parse_args()

    if args.selftest:
        sys.exit(run_selftest())

    if not args.script or not args.audio:
        ap.error('the following arguments are required: script, audio')

    try:
        lines = parse_script_lines(args.script)
    except (OSError, UnicodeDecodeError, ValueError) as e:
        print(f'error: could not read script {args.script}: {e}', file=sys.stderr)
        sys.exit(2)
    if not lines:
        print(f'error: no dialogue lines found in {args.script} '
              f'(wrong file, or SCRIPT/AUDIO arguments swapped?)', file=sys.stderr)
        sys.exit(2)

    lexicon_path = args.lexicon or default_sidecar_path(args.script, 'lexicon.txt')
    ignore_path = args.ignore or default_sidecar_path(args.script, 'qa-ignore.txt')
    try:
        ignore_pairs = load_ignore_file(ignore_path) | load_lexicon_ignore_pairs(lexicon_path)

        if args.transcript:
            with open(args.transcript, encoding='utf-8') as f:
                heard_text = f.read()
        else:
            with tempfile.TemporaryDirectory() as td:
                heard_text = transcribe(args.audio, td, model_override=args.model)
            write_transcript(transcript_path_for(args.audio), heard_text)
    except (OSError, subprocess.CalledProcessError, ValueError, UnicodeDecodeError) as e:
        print(f'error: {e}', file=sys.stderr)
        sys.exit(2)

    report = analyze(lines, heard_text, ignore_pairs, args.threshold,
                      min_coverage_tokens=args.min_coverage_tokens)

    for rl in report['report_lines']:
        print(rl)
    gates = ', '.join(report['gates']) if report['gates'] else 'none'
    if report['coverage_gated']:
        coverage_note = f'(threshold {args.threshold})'
    else:
        coverage_note = (f'(informational — script too short to gate on: '
                          f'{report["expected_token_count"]} < {args.min_coverage_tokens} tokens)')
    print(f'\ncoverage: {report["coverage"]:.4f} {coverage_note}  flagged lines: {report["flagged_line_count"]}  '
          f'dropped lines: {report["dropped_line_count"]}  failing: {gates}')

    if args.json_out:
        try:
            out = dict(report)
            out['ops'] = [{**o, 'expected': list(o['expected']), 'heard': list(o['heard'])} for o in out['ops']]
            with open(args.json_out, 'w', encoding='utf-8') as f:
                json.dump(out, f, indent=2)
        except OSError as e:
            print(f'error: could not write --json output to {args.json_out}: {e}', file=sys.stderr)
            sys.exit(2)

    sys.exit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
