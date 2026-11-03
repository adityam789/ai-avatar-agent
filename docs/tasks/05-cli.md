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
