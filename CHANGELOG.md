# Changelog

## 0.1.0 — 2026-11-03
First tagged release (portfolio clean-up of the original prototype).

* Packaged as `ai_avatar` (`src/` layout) with a pydantic config, an `ai-avatar` CLI (`run`, `research`, `script`, `doctor`) and `python -m ai_avatar`.
* Staged, resumable pipeline with per-run directories, `run.json`, `--resume` / `--from-stage` / `--only-stage`, overrides and a shared planner for `--dry-run`.
* Fail-soft research with wall-clock timeouts, DuckDuckGo default search provider (Google CSE deprecated), optional Reddit, disk cache and offline fixtures.
* LLM client with retries, backoff, model fallback and a `FakeLLM`; word-budgeted, TTS-sanitised script stage.
* Lazy XTTS v2 with device resolution, SadTalker wrapper that never edits the submodule, tested ffmpeg composer, `FakeTTS` / `FakeAvatar` for `--offline` mode.
* Secrets hygiene: `.env.example`, redaction of secrets in logs/errors/`run.json`.
* 400+ tests (97 % branch coverage), ruff, GitHub Actions workflow (3.10/3.11), pre-commit, Makefile.
* Generated placeholder avatar and background loop replace third-party media.
