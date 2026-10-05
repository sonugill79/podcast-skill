# Changelog

## 0.2.1

- Fix: audio QA broke on fresh installs. faster-whisper 1.2.1 passes an argument PyAV 19 removed, and av was
  unpinned; it is now `av>=11,<19`. The install smoke test transcribes a real WAV file, so this kind of break fails at
  install time. Existing installs with av 19 show "QA: <level> (needs repair)"; `upgrade qa` (or auto_setup) fixes it
  in place, ~35 MB, model kept. Until then qa.py exits 3 saying it needs a repair instead of crashing.
