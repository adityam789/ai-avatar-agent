# 05 — CLI and `__main__`

## Goal
A friendly, documented entry point that is resume-demo ready.

## Steps
1. `cli.py` using `argparse` (or `typer` if added as dep): subcommands
   - `ai-avatar run TOPIC [--config F] [--avatar-image P] [--loop P] [--audio P] [--script-file P] [--resume DIR] [--from-stage S] [--no-background] [--device cpu|cuda|mps] [--seed N] [-v/-q]`
   - `ai-avatar doctor` — checks Python version, ffmpeg/ffprobe, torch availability/device, SadTalker checkpoints present, TTS model cached, env var NAMES set/unset (never values).
   - `ai-avatar research TOPIC` and `ai-avatar script TOPIC` — run partial pipelines for debugging.
2. `__main__.py` so `python -m ai_avatar ...` works; `run.py` becomes a 5-line shim.
3. Nice exit codes and error messages (no tracebacks for expected failures unless `-v`).
4. Shell completion not needed. Keep help text crisp; README quickstart will quote it.

## Acceptance criteria
- `python -m ai_avatar --help`, `ai-avatar doctor`, `ai-avatar run "OpenAI" --dry-run` all work on a machine without GPU/torch (doctor reports what's missing).

## Results (2026-11-03)
- `ai_avatar/cli.py` (argparse): `run`, `research`, `script`, `doctor`, `--version`; `python -m ai_avatar` and `run.py` are 5-line shims.
- `run` flags: all listed in the task plus `--dry-run` and `--offline` (sets `cfg.offline`; the offline fakes themselves arrive in Tasks 06-08).
  `--seed` seeds `random`, and numpy/torch if installed (SadTalker itself has no seed knob, so full determinism is not guaranteed).
- CLI paths (`--audio`, `--resume`, `--avatar-image`, ...) are resolved against the CWD; config-file paths against the project root.
  `-v/-q/--config` go after the subcommand (`ai-avatar doctor -v`). `--from-stage/--only-stage` are mutually exclusive and, past
  `research`, need `--resume`/`--audio`/`--script-file`. `--seed` is validated (0..2**32-1) but not recorded in `run.json`.
- `--device` only affects XTTS (only `cuda` enables the GPU today); SadTalker ignores it. **Task 08 TODO.**
- Exit codes: 0 ok, 1 expected failure (`AiAvatarError`, bad config, failed dry-run/doctor), 2 usage, 70 unexpected, 130 Ctrl-C.
  Tracebacks only with `-v`, always scrubbed with `redact.scrub`.
- `doctor` = `checks.check_runtime()` (python, torch + device, TTS pkg, XTTS cache, praw) + `check_environment()`. It exits 1 only for
  *core* problems (python version, ffmpeg, ffprobe); torch/TTS/checkpoints/API keys are reported as `warn` ("not ready for a real run").
  Env vars are reported by name as set/unset only.
- `run --dry-run` exits 1 if a *required* check fails. `pipeline.planned_stages()` is the single planner (also called by `run` before it
  creates/copies/deletes anything): it validates options, the resume dir (exists, `run.json` readable, same topic) and that every planned
  stage finds its input. The dry-run requires the API key only if research/script will run, the TTS package only for tts, torch for
  tts/avatar, and none of them with `--offline`. (Offline still lists checkpoint/avatar checks as required:
  **Task 08/09: make `check_environment` offline-aware.**)
- Verified manually from `/` in a venv with `.[dev]` only: `python -m ai_avatar --help`, `ai-avatar doctor` (exit 0, torch/TTS warned),
  `ai-avatar run "OpenAI" --dry-run` (plan + checks; real `.env` loaded, values not printed), bad override -> `error:` + exit 1.
- Also (not a numbered task, commit `741efb2`): stage functions now all take `Config`, `Config` gained the fields Tasks 06-08 need,
  and `llm.build_llm(cfg)` is the single LLM seam, so the parallel tasks don't edit shared config/pipeline code.
- Review round 1: FAIL (7 findings: doctor FAIL/warn mismatch, CWD vs project-root paths, unguarded torch import, misleading dry-run,
  weak tests, unvalidated seed, flag combos). All fixed; tests 59 -> 68.
- Review round 2: dry-run still ignored which stages run (required torch/TTS/key for `--only-stage compose`), accepted combos `run()` rejects.
  Fixed: `pipeline.validate_options()` (shared by `run` and dry-run) and `pipeline.planned_stages()` (consistency-tested against `run` over 13
  scenarios) drive the dry-run: key needed only if research/script run, TTS pkg only for tts, torch for tts/avatar.
- Review round 3: dry-run could still say Ready for resumes `run()` rejects (missing stage inputs, topic mismatch/corrupt run.json) and the
  planner diverged on same-file overrides. Fixed at the root: `planned_stages` is now the one planner used by both, validates inputs, topic
  and run.json, and `run` calls it before touching anything (so an impossible plan changes nothing). This last fix had no 4th review (3-round cap);
  covered by new parametrized + CLI tests (88 total).
