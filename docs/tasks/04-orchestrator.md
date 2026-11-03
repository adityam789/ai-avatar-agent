# 04 — Orchestrator: real pipeline, run directories, resumability

## Goal
`pipeline.run(topic, cfg)` executes all stages for real and leaves an inspectable run folder.

## Context
Current `orchestrator.run` ignores `topic`: script/TTS are commented out and it reuses a fixed wav and image.

## Steps
1. Define a `Stage` protocol or simple functions with explicit inputs/outputs; a `RunContext` dataclass holding `run_id`, `run_dir`, config, and artifact paths.
2. Run layout: `outputs/<YYYYmmdd-HHMMSS>-<slug-of-topic>/{research.json,script.txt,audio.wav,avatar.mp4,final.mp4,run.json}`. `run.json` records topic, timings per stage, model names, versions, config hash. Never write secrets into it.
3. Resumability: if an artifact exists and `--resume <run_dir>` is given, skip that stage. Also support `--from-stage` / `--only-stage` and `--audio PATH` / `--script-file PATH` overrides for offline iteration (this replaces the hard-coded paths).
4. Return the avatar path explicitly from the avatar stage (no `sorted(glob)[-1]`).
5. Stage timing + structured logging via `logging` (no `print`). Clear, typed exceptions (`ResearchError`, `LLMError`, `TTSError`, `AvatarError`, `ComposeError`) with actionable messages.
6. If `background.enabled` is false, copy avatar video to final instead of the current `rename` (rename breaks across filesystems and moves the intermediate).
7. Add a `--dry-run` that validates config, checks ffmpeg/model paths/env var presence (names only) and prints the plan.

## Acceptance criteria
- Running with a mocked set of stages produces the expected run folder and `run.json`.
- Re-running with `--resume` skips completed stages.
- Topic actually flows into research and script.
