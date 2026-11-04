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

## Results (2026-11-03)
- `pipeline.run(topic, cfg, resume=, from_stage=, only_stage=, audio=, script_file=, stages=)` + `pipeline.dry_run()`.
  Stages are `Stage(name, artifact, fn, error, requires)` records; tests inject fakes via `stages=`.
- Skip rule: a stage is skipped if its artifact *or any later stage's artifact* exists (so `--script-file` skips research,
  `--audio` skips research+script+tts). `from_stage` forces that stage and later ones; `only_stage` runs just one.
- Re-running a stage (forced, or via an override) deletes its old artifact and every later stage's artifact first, so `--resume` can
  never trust stale downstream output. Any failure, including Ctrl-C, deletes the stage's partial artifact and is recorded in
  `run.json`. `--resume` with a different topic, or a corrupt `run.json`, is a `PipelineError`. Run dirs never collide (`-2` suffix).
- Typed errors in `errors.py`; unexpected stage exceptions are wrapped as the stage's error type (`LLMError` for script, `TTSError`, ...);
  a missing optional dependency yields `pip install -e '.[tts]'`-style hints. `run.json` records installed tts/torch versions.
  Not done: ffmpeg stderr capture (Task 08), the model that actually answered (Task 07).
- `stages/avatar.py` now returns the *new* mp4 found in the per-run `sadtalker/` result dir (before/after set difference, no
  `sorted(glob)[-1]` over a shared dir). Whether SadTalker writes exactly one top-level mp4 could not be verified (no GPU/weights).
- `stages/script.py` now takes `facts` (research is its own stage); `research.reddit_creds_from_env()` added.
- `checks.py` (shared with Task 05 `doctor`): ffmpeg/ffprobe, avatar image, loop, SadTalker checkpoints, env var **names** only.
- `print` remains only in `__main__.py` (interim, replaced by the CLI in Task 05) and in `research/aggregator.py:17` (Task 06 removes it). Lint: ruff config + formatting is Task 09 (ad-hoc `ruff check` shows only import ordering
  in files not yet touched).
- Notes for later tasks: CLI (05) must call `load_dotenv()` before `dry_run`/`run`; research still crashes without Reddit creds
  (Task 06); LLM client/script still hard-code model and wrap nothing (Task 07); TTS device handling (Task 08).

- Review round 1: FAIL (stale downstream artifacts after failed forced rerun, overrides ignored with resume, Ctrl-C leaves partial files,
  wrong error type for script, false print claim, adapters untested). All fixed; mutation-checked that the new tests fail without the fixes.
- Review round 2: found a secret-leak path (requests errors embed `?key=...` URLs -> run.json / error text), stale `run.json` stage
  records after invalidation, overrides silently discarded by forced stages, `only_stage` deleting later artifacts. Fixed:
  `redact.scrub()` (env values + URL credentials) is applied to everything derived from exceptions; invalidation also drops stage
  records; conflicting override+from/only stage is a `PipelineError`; `only_stage` no longer deletes anything (warns that later
  artifacts are stale); `run.json` is written before the first stage. **Task 06/07 must route exception text through `redact.scrub`.**
- Review round 3: PASS on the round-2 fixes; 4 smaller findings fixed afterwards **without a fourth review** (3-round cap): overrides now
  must target the stage they feed (`from/only_stage` == stage after the last override, checked before anything is touched); logging
  handlers scrub records (urllib3 logs `?key=...` at DEBUG); `scrub()` only blanks *secret* env vars (flag in `checks.ENV_VARS`).
  Known remaining: `raise ... from exc` keeps the raw cause, so the CLI (Task 05) must print only `str(err)` for `AiAvatarError` and
  show tracebacks only at `-v` (where the logging filter does not cover tracebacks).
