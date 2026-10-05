#!/usr/bin/env python3
"""check_sources.py: the deterministic half of "facts only from Verified" for the eval fixtures.

Every topic's sources.md lists its "Reported, not re-verified" (R#) and "Don't air" (D#) rows with a `key`, a
phrase that identifies the claim when it is said. For every fixture script.txt under the topic:

  - a Don't-air key in any dialogue line fails (it must never be said, hedged or not);
  - a Reported key in a dialogue line fails unless that same line also hedges it ("reported", "claims",
    "couldn't verify", "unconfirmed", ...), so a Reported item is never said as fact.

This is a floor, not the whole check: the judged rubric (rubric.md, row `facts_from_verified`) still reads every
fact against the Verified rows. Stdlib only. Exit 0 = clean, 1 = a violation, 2 = bad input.

  python3 test/pacing/check_sources.py [FIXTURES_DIR]     (default: the fixtures/ folder beside this file)
  python3 test/pacing/check_sources.py --selftest
"""
import os
import re
import sys

HEDGE_RE = re.compile(r"\b(report(?:s|ed)?|claims?|claimed|said in an interview|unverified|unconfirmed|"
                      r"(?:couldn't|could not|can't|cannot) (?:verify|confirm|check)|not verified|allegation|"
                      r"alleged?)\b", re.I)
SPEAKER_RE = re.compile(r'^([A-Z]+):\s*(.+)$')
ROW_RE = re.compile(r'^\|\s*([RD]\d+)\s*\|')


def read_keys(sources_path):
    """{'R1': 'key phrase', 'D1': ...} from the R#/D# table rows (the key is the last cell)."""
    keys = {}
    with open(sources_path, encoding='utf-8') as f:
        for line in f:
            m = ROW_RE.match(line)
            if not m:
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if len(cells) < 3 or not cells[-1]:
                raise ValueError(f'{sources_path}: row {m.group(1)} has no key in its last column')
            keys[m.group(1)] = cells[-1].lower()
    return keys


def check_script(script_path, keys):
    """[(line_no, row_id, message)] for each violation in one script."""
    problems = []
    with open(script_path, encoding='utf-8') as f:
        for n, raw in enumerate(f, 1):
            m = SPEAKER_RE.match(raw.strip())
            if not m:
                continue
            text = m.group(2).lower()
            for row, key in keys.items():
                if key not in text:
                    continue
                if row.startswith('D'):
                    problems.append((n, row, f"Don't-air item said on air (key {key!r})"))
                elif not HEDGE_RE.search(text):
                    problems.append((n, row, f'Reported item said without a hedge on the same line (key {key!r})'))
    return problems


def fixtures(root):
    """[(script_path, sources_path)] for every script.txt whose topic folder (an ancestor) has sources.md."""
    out = []
    for dirpath, _dirs, files in sorted(os.walk(root)):
        if 'script.txt' not in files:
            continue
        d = dirpath
        while True:
            cand = os.path.join(d, 'sources.md')
            if os.path.isfile(cand):
                out.append((os.path.join(dirpath, 'script.txt'), cand))
                break
            if os.path.abspath(d) == os.path.abspath(root):
                raise ValueError(f'{dirpath}: no sources.md for this fixture')
            d = os.path.dirname(d)
    return sorted(out)


def run(root):
    found = fixtures(root)
    if not found:
        print(f'{root}: no fixtures found', file=sys.stderr)
        return 2
    bad = 0
    for script, sources in found:
        keys = read_keys(sources)
        rel = os.path.relpath(script, root)
        problems = check_script(script, keys)
        for n, row, msg in problems:
            print(f'  FAIL {rel}:{n} {row}: {msg}')
        bad += bool(problems)
        if not problems:
            print(f'  ok   {rel} ({sum(k.startswith("R") for k in keys)} reported, '
                  f'{sum(k.startswith("D") for k in keys)} do-not-air keys)')
    print(f'sources check: {len(found) - bad}/{len(found)} fixtures clean')
    return 1 if bad else 0


def selftest():
    import tempfile
    ok = True

    def check(name, cond):
        nonlocal ok
        print(('  ok   ' if cond else '  FAIL ') + name)
        ok = ok and bool(cond)

    with tempfile.TemporaryDirectory() as d:
        topic = os.path.join(d, 'topic')
        os.makedirs(os.path.join(topic, 'a'))
        with open(os.path.join(topic, 'sources.md'), 'w') as f:
            f.write('| # | Claim | Source | key |\n|---|---|---|---|\n'
                    '| R1 | it cost four million | paper | four million |\n'
                    '| D1 | it cracked | forum | cracked |\n')
        keys = read_keys(os.path.join(topic, 'sources.md'))
        check('keys are read from the last column', keys == {'R1': 'four million', 'D1': 'cracked'})
        s = os.path.join(topic, 'a', 'script.txt')

        def probs(text):
            with open(s, 'w') as f:
                f.write(text)
            return check_script(s, keys)

        check('a hedged Reported item passes',
              probs('MAYA: A paper reported it cost four million. We couldn\'t verify it.\n') == [])
        check('a Reported item said as fact fails', [p[1] for p in probs('ALEX: It cost four million.\n')] == ['R1'])
        check("a Don't-air item fails even when hedged",
              [p[1] for p in probs('ALEX: A forum post claims it cracked.\n')] == ['D1'])
        check('comments and pauses are not dialogue', probs('# it cracked\n[pause 1]\n') == [])
        probs('ALEX: It cost four million.\n')
        check('run() exits 1 on a violation', run(d) == 1)
        probs('MAYA: Nothing here.\n')
        check('run() exits 0 when clean', run(d) == 0)
    print('selftest: ' + ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    args = sys.argv[1:]
    if args == ['--selftest']:
        sys.exit(selftest())
    root = args[0] if args else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
    try:
        sys.exit(run(root))
    except (OSError, ValueError) as e:
        print(f'check_sources: {e}', file=sys.stderr)
        sys.exit(2)
