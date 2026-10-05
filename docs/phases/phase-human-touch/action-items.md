# Phase Human Touch: Action Items

| ID | Action | Owner | Due / trigger |
|---|---|---|---|
| A1 | New phase **Expressive Voice**: opt-in `upgrade voice-expressive` on Qwen3-TTS-1.7B-Base. Host clones from Kokoro reference clips; plugin timing reused; per-chunk whisper check with retries; sized (≈ 11 GB) and GPU-gated, with Kokoro as fallback (E12–E14, E20, E21) | orchestrator | next phase |
| A2 | QA: before failing DROPPED/MISSING on a long file, re-transcribe the flagged line's audio slice alone (ledger L38) | orchestrator | Expressive Voice phase (or 0.3.x) |
| A3 | Push 0.2.1 (PyAV fix) and 0.3.0 once the owner gives the go-ahead | owner | on approval |
| A4 | Upstream the four retro lessons to the phase-gates skill | orchestrator | after release |
| A5 | Send the final episode informally to the original feedback-givers and record their replies (not a gate) | owner | after release |
| A6 | Delete the scratch Qwen/Chatterbox installs (~39 GB) once A1 starts with its own installer | orchestrator | A1 kickoff |
| A7 | setup.sh: check `${#STATE_DIR}` before the 521 MB kokoro download and point at a short `PODCAST_STATE_DIR` (ledger L40) | orchestrator | next phase |
