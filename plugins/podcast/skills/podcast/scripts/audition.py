#!/usr/bin/env python3
"""
audition.py: hear every voice, and measure it.

Synthesizes one identical sentence in each voice, writes a single MP3 where each
voice announces itself and then reads the line, and a JSON table of measured
pitch, pace and level. Picking a cast by name alone is guesswork; this is how
casts/VOICES.md was built.

  audition.py [OUT.mp3] [--grep SUBSTR] [--engine ...] [--text "..."] [--json FILE]
  audition.py --grep am_ american-men.mp3     only voices whose id contains "am_"
  audition.py --grep af_,am_,bf_,bm_          the 28 English voices
  audition.py --list                          print the voice ids and exit
  audition.py --selftest                      offline checks, exits 0/1

Measured per voice, all at speed 1.0 so the numbers describe the voice itself:
  pitch   median fundamental (Hz), by autocorrelation over voiced frames
  pace    words per minute for the fixed sentence -- the voice's own tempo
  level   RMS dBFS before loudnorm; a very low value means a hissier episode

Exit codes: 0 ok · 2 bad arguments · 3 no voice engine installed (or the engine
has no listable voices -- only the kokoro engines do).
"""
import argparse, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render  # noqa: E402  -- engine selection, ffmpeg resolution, die()

DEFAULT_TEXT = ("The filings say one thing and the press release says another, "
                "so let's start with what everyone actually agrees on.")


def measure(audio, sr, text):
    """{'f0','wpm','rms_db','peak_db','sec'} for one rendered line."""
    import numpy as np
    a = np.asarray(audio, dtype=np.float32)
    if not len(a):
        return {'f0': 0, 'wpm': 0, 'rms_db': -999.0, 'peak_db': -999.0, 'sec': 0.0}
    rms = float(20 * np.log10(max(float(np.sqrt(np.mean(a ** 2))), 1e-9)))
    peak = float(20 * np.log10(max(float(np.max(np.abs(a))), 1e-9)))
    sec = len(a) / sr
    return {'f0': round(estimate_f0(a, sr)), 'wpm': round(len(text.split()) / (sec / 60)),
            'rms_db': round(rms, 1), 'peak_db': round(peak, 1), 'sec': round(sec, 2)}


def estimate_f0(a, sr, lo_hz=60, hi_hz=350, silence=0.02, voiced=0.3):
    """Median fundamental over frames with enough energy and a clear period.

    Autocorrelation rather than a library: this has to run in the same venv as the
    engine, and adding a pitch dependency to hear a voice is a bad trade."""
    import numpy as np
    n, hop = int(0.04 * sr), int(0.02 * sr)
    # ceil on the short lag / floor on the long one: rounding the other way lets the
    # window report a frequency just outside the band it was asked for (int(24000/350)
    # = 68 samples, which is 352.9 Hz).
    lo, hi = int(math.ceil(sr / hi_hz)), int(sr / lo_hz)
    if n <= 0 or hi <= lo or len(a) < n:
        return 0.0
    found = []
    for i in range(0, len(a) - n, hop):
        frame = a[i:i + n]
        if float(np.sqrt(np.mean(frame ** 2))) < silence:
            continue
        frame = frame - frame.mean()
        ac = np.correlate(frame, frame, 'full')[n - 1:]
        if ac[0] <= 0 or hi > len(ac):
            continue
        seg = ac[lo:hi]
        if not len(seg):
            continue
        peak = int(np.argmax(seg)) + lo
        if ac[peak] / ac[0] > voiced:
            found.append(sr / peak)
    return float(np.median(found)) if found else 0.0


# Voice id prefixes: first letter is the language, second is the gender.
LANGUAGES = {'a': 'American', 'b': 'British', 'e': 'Spanish', 'f': 'French',
             'h': 'Hindi', 'i': 'Italian', 'j': 'Japanese', 'p': 'Portuguese',
             'z': 'Mandarin'}
GENDERS = {'f': 'female', 'm': 'male'}


def spoken_id(voice_id):
    """"af_kore" -> "A. F. Kore." -- letters spelled out so a listener can write the
    id down. Without the full stops the engine reads "af" as a word."""
    prefix, _, name = voice_id.partition('_')
    if not name:
        return f'{voice_id}.'
    return ''.join(f'{c.upper()}. ' for c in prefix) + name.capitalize() + '.'


def describe(voice_id, m=None):
    """The spoken card for one voice: who it is, then how it measures.

    The numbers are what make the audition usable -- hearing "one hundred and
    twenty words per minute" while listening to a slow voice is what connects the
    impression to the row in VOICES.md."""
    prefix = voice_id.partition('_')[0]
    lang = LANGUAGES.get(prefix[:1], '')
    gender = GENDERS.get(prefix[1:2], '')
    who = ' '.join(x for x in (lang, gender) if x)
    parts = [spoken_id(voice_id)]
    if who:
        parts.append(who + '.')
    if m and m.get('f0') and m.get('wpm'):
        parts.append(f"{m['f0']} hertz, {m['wpm']} words per minute.")
    return ' '.join(parts)


def chapter_starts(segment_seconds):
    """Running start time of each segment. One chapter per voice is what makes a
    54-voice audition navigable -- a player shows the list and you jump."""
    starts, t = [], 0.0
    for sec in segment_seconds:
        starts.append(round(t, 3))
        t += sec
    return starts, round(t, 3)


def format_table(rows):
    out = [f"{'voice':14} {'pitch':>6} {'pace':>6} {'level':>8}"]
    for r in sorted(rows, key=lambda r: r['voice']):
        out.append(f"{r['voice']:14} {r['f0']:>4} Hz {r['wpm']:>4} w {r['rms_db']:>6} dB")
    if rows:
        paces = sorted(r['wpm'] for r in rows)
        out.append(f"\nmedian pace {paces[len(paces) // 2]} wpm across {len(rows)} voices")
    return '\n'.join(out)


def select_voices(all_ids, grep):
    """Filter by one substring or a comma-separated list of them, order preserved."""
    if not grep:
        return list(all_ids)
    wanted = [g.strip() for g in grep.split(',') if g.strip()]
    return [v for v in all_ids if any(w in v for w in wanted)]


def engine_voice_ids(engine_id):
    """Every voice the engine can speak. Only the kokoro engines can enumerate
    themselves; piper's voices are separate model files, so there is nothing to
    audition beyond the two that setup.sh downloads."""
    if not (engine_id or '').startswith('kokoro'):
        render.die(f'{engine_id}: this engine cannot list its voices -- audition needs kokoro', 3)
    return sorted(render.KOKORO_VOICE_IDS)


def build_arg_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument('out', nargs='?', default='audition.mp3')
    ap.add_argument('--grep', default=None,
                     help='only voices whose id contains this; comma-separated for '
                          'several (--grep af_,am_,bf_,bm_ = the English voices)')
    ap.add_argument('--engine', default=None)
    ap.add_argument('--text', default=DEFAULT_TEXT)
    ap.add_argument('--json', default=None, help='measurements file (default: OUT with .json)')
    ap.add_argument('--list', action='store_true', help='print matching voice ids and exit')
    ap.add_argument('--selftest', action='store_true')
    return ap


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    if args.selftest:
        sys.exit(run_selftest())

    engine_id = render.select_engine(args.engine)
    # Same contract as render.py: called with plain `python3`, the script finds its
    # own runtime. numpy/soundfile/kokoro live in the managed venv, not the system
    # interpreter, so re-exec there before importing any of them.
    render.maybe_reexec_into_venv(engine_id)
    ids = select_voices(engine_voice_ids(engine_id), args.grep)
    if not ids:
        render.die(f'--grep {args.grep!r} matched none of the {len(engine_voice_ids(engine_id))} voices', 2)
    if args.list:
        print('\n'.join(ids))
        return 0

    import numpy as np
    import soundfile as sf
    engine = render.make_engine(engine_id, {v: v for v in ids})
    sr = engine.sample_rate
    rows, pieces, segment_seconds = [], [], []
    for i, v in enumerate(ids, 1):
        print(f'\r  {i}/{len(ids)}  {v:14}', end='', flush=True)
        # The line is synthesized first so the announcement can quote the voice's
        # own measured pitch and pace back to the listener.
        audio, _ = engine.synth(args.text, v, 1.0)
        m = measure(audio, sr, args.text)
        rows.append(dict(voice=v, **m))
        intro, _ = engine.synth(describe(v, m), v, 1.0)
        seg = [np.asarray(intro, np.float32), np.zeros(int(0.35 * sr), np.float32),
               np.asarray(audio, np.float32), np.zeros(int(0.8 * sr), np.float32)]
        segment_seconds.append(sum(len(x) for x in seg) / sr)
        pieces += seg
    print()

    starts, total = chapter_starts(segment_seconds)
    chapters = [{'title': f"{i}. {v}", 'start': st}
                for i, (v, st) in enumerate(zip(ids, starts), 1)]
    for row, st in zip(rows, starts):
        row['start'] = st

    wav = os.path.splitext(args.out)[0] + '.audition.wav'
    sf.write(wav, np.concatenate(pieces), sr)
    render.encode_mp3(wav, args.out,
                      {'title': 'Voice audition', 'album': 'Podcast', 'genre': 'Podcast',
                       'comment': f'{len(ids)} voices, one chapter each.'},
                      chapters, total)
    os.remove(wav)
    json_path = args.json or os.path.splitext(args.out)[0] + '.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(rows, f, indent=1)
    print(format_table(rows))
    print()
    for c in chapters:
        print(f'  {render.fmt_mmss(c["start"])}  {c["title"]}')
    print(f'\n✓ {args.out}  ({len(rows)} voices)   measurements: {json_path}')
    return 0


def run_selftest():
    import math
    ok = True

    def check(name, cond):
        nonlocal ok
        print(('PASS' if cond else 'FAIL') + f'  {name}')
        if not cond:
            ok = False

    try:
        import numpy as np
    except ImportError:
        print('SKIP  numpy not installed -- measurement checks need it')
        return 0


    sr = 24000
    t = np.arange(int(sr * 0.5)) / sr

    # estimate_f0 against tones of known frequency.
    for hz in (100, 150, 220):
        tone = (0.5 * np.sin(2 * math.pi * hz * t)).astype(np.float32)
        got = estimate_f0(tone, sr)
        check(f'f0 of a {hz} Hz tone is within 2 Hz (got {got:.1f})', abs(got - hz) < 2)
    check('f0 of silence is 0', estimate_f0(np.zeros(sr, np.float32), sr) == 0.0)
    check('f0 of a too-short buffer is 0', estimate_f0(np.zeros(10, np.float32), sr) == 0.0)
    # A 30 Hz tone is below the search window, so its period is never found; what
    # matters is that the result stays inside the band rather than reporting 30.
    sub = estimate_f0((0.5 * np.sin(2 * math.pi * 30 * t)).astype(np.float32), sr)
    check('a sub-60 Hz tone is never reported at its true frequency',
          sub == 0.0 or 60 <= sub <= 350)
    check('every measured pitch stays inside the searched band',
          all(estimate_f0((0.5 * np.sin(2 * math.pi * hz * t)).astype(np.float32), sr) in (0.0,)
              or 60 <= estimate_f0((0.5 * np.sin(2 * math.pi * hz * t)).astype(np.float32), sr) <= 350
              for hz in (30, 100, 220, 500)))

    # measure(): level, pace and duration.
    half = (0.5 * np.sin(2 * math.pi * 150 * t)).astype(np.float32)
    m = measure(half, sr, 'one two three')
    check('rms of a 0.5-amplitude sine is about -9 dB', abs(m['rms_db'] + 9.0) < 0.5)
    check('peak of a 0.5-amplitude sine is about -6 dB', abs(m['peak_db'] + 6.0) < 0.5)
    check('duration is measured from the sample count', abs(m['sec'] - 0.5) < 0.01)
    check('3 words in 0.5 s reads as 360 wpm', m['wpm'] == 360)
    check('an empty buffer measures without dividing by zero',
          measure(np.zeros(0, np.float32), sr, 'x')['wpm'] == 0)

    # spoken_id() / describe(): the announcement has to be intelligible, and has to
    # carry the numbers -- that is the whole point of an audition over a voice list.
    check('spoken id spells the prefix as letters', spoken_id('af_kore') == 'A. F. Kore.')
    check('spoken id capitalises the name', spoken_id('bm_george') == 'B. M. George.')
    check('spoken id handles an id with no underscore', spoken_id('solo') == 'solo.')
    d = describe('af_kore', {'f0': 148, 'wpm': 174})
    check('describe names the id', d.startswith('A. F. Kore.'))
    check('describe names language and gender', 'American female' in d)
    check('describe speaks the measurements', '148 hertz' in d and '174 words per minute' in d)
    check('describe of a British male reads correctly',
          'British male' in describe('bm_lewis', {'f0': 85, 'wpm': 176}))
    check('describe covers every language prefix in the pack',
          all(LANGUAGES.get(v[0]) for v in engine_voice_ids('kokoro')))
    check('describe covers every gender prefix in the pack',
          all(GENDERS.get(v[1]) for v in engine_voice_ids('kokoro')))
    check('describe without measurements still names the voice',
          describe('af_kore') == 'A. F. Kore. American female.')
    check('describe skips a failed measurement rather than saying zero',
          'hertz' not in describe('af_kore', {'f0': 0, 'wpm': 0}))

    # format_table()
    table = format_table([{'voice': 'af_kore', 'f0': 148, 'wpm': 174, 'rms_db': -18.3},
                           {'voice': 'am_adam', 'f0': 117, 'wpm': 187, 'rms_db': -18.3}])
    check('table lists every voice', 'af_kore' in table and 'am_adam' in table)
    check('table reports the median pace', 'median pace 187 wpm' in table)
    check('table of nothing does not crash', 'voice' in format_table([]))

    # chapter_starts(): the offsets a player uses to jump between voices.
    starts, total = chapter_starts([2.0, 3.5, 1.25])
    check('first chapter starts at zero', starts[0] == 0.0)
    check('each chapter starts where the last ended', starts == [0.0, 2.0, 5.5])
    check('total is the sum of the segments', total == 6.75)
    check('no segments -> no chapters and zero length', chapter_starts([]) == ([], 0.0))
    check('chapter starts are strictly increasing for real segments',
          all(b > a for a, b in zip(starts, starts[1:])))

    # engine_voice_ids(): kokoro only, and it must agree with render's list.
    check('kokoro lists all 54 voices', len(engine_voice_ids('kokoro')) == 54)
    check('kokoro-torch lists the same voices',
          engine_voice_ids('kokoro-torch') == engine_voice_ids('kokoro'))
    try:
        engine_voice_ids('piper')
    except SystemExit as e:
        check('piper exits 3 -- it has no listable voice pack', e.code == 3)
    else:
        check('piper exits 3 -- it has no listable voice pack', False)

    # --grep is what makes this usable on one family at a time.
    ap = build_arg_parser()
    check('--grep is parsed', ap.parse_args(['--grep', 'am_']).grep == 'am_')
    check('out defaults to audition.mp3', ap.parse_args([]).out == 'audition.mp3')
    all_ids = engine_voice_ids('kokoro')
    check('--grep am_ selects the 9 American male voices',
          len(select_voices(all_ids, 'am_')) == 9)
    check('--grep bf_ selects the 4 British female voices',
          len(select_voices(all_ids, 'bf_')) == 4)
    check('--grep with a comma list selects the 28 English voices',
          len(select_voices(all_ids, 'af_,am_,bf_,bm_')) == 28)
    check('--grep tolerates spaces around the commas',
          select_voices(all_ids, 'af_, am_') == select_voices(all_ids, 'af_,am_'))
    check('no --grep selects everything', len(select_voices(all_ids, None)) == 54)
    check('--grep matching nothing returns nothing', select_voices(all_ids, 'zz_') == [])

    print(('PASS' if ok else 'FAIL') + '  audition selftest')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
