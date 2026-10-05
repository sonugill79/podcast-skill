# Changelog

## 0.3.0

- Script rules: on two-host, Maya is the educator and Alex the learner for the whole episode. She teaches one idea
  per turn; he states the puzzle, guesses before a reveal and explains it back. He never supplies a fact she has not
  given, and a wrong guess is a misconception the research recorded. Scripts are self-checked line by line against
  `sources.md` before rendering.
- Pauses where a listener needs them: a gap after every sentence, thinking beats inside a line (`[pause N]`), and
  holds written as `...`.
- `--pacing brisk|relaxed|spacious`: silence between sentences and speakers. Default `relaxed`; `brisk` reproduces
  0.2.0 audio. Switching to or from `brisk` re-voices each line once.
- `--level intro|informed|expert`: how much the listener already knows. Default `informed`.
- `--focus "a, b, c"`: up to three aspects to spend more of the episode on; topics only.
- "Go deeper on <aspect>" makes a follow-up episode in a new folder beside the parent, which is never modified.
- New plugin settings: `default_pacing` (relaxed) and `default_level` (informed).
- `render.py --dry-run` prints a pacing check; with `--strict` it exits 4 on a warning.
- Voice rotation per cast, a voice blocklist (`voice_blocklist`), and a voice guide for choosing voices.

## 0.2.1

- Fix: audio QA broke on fresh installs. faster-whisper 1.2.1 passes an argument PyAV 19 removed, and av was
  unpinned; it is now `av>=11,<19`. The install smoke test transcribes a real WAV file, so this kind of break fails at
  install time. Existing installs with av 19 show "QA: <level> (needs repair)"; `upgrade qa` (or auto_setup) fixes it
  in place, ~35 MB, model kept. Until then qa.py exits 3 saying it needs a repair instead of crashing.
