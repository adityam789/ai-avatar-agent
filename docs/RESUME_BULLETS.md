# Resume bullets, talk track, retrospective

All numbers below are from this repository as of v0.1.0 (≈2,800 lines of source, ≈3,700 lines of tests, 401 tests, 97 % branch coverage,
`pytest` ≈ 10 s with no GPU or network). Claims are limited to what exists and was run here; the real XTTS/SadTalker stages and live
web/LLM calls are covered by mocked tests only.

## Bullet options (pick 3–5)

1. **Built an end-to-end AI video pipeline in Python** that turns a topic into a 1080×1920 talking-head video — research (RSS / web search / Reddit) → LLM script (OpenRouter)
   → neural TTS (Coqui XTTS v2) → talking-head animation (SadTalker) → ffmpeg composite — as five independently testable, resumable stages.
2. **Designed the pipeline around file artifacts and a single planner**: each stage writes one file into a run directory, so runs can be resumed, partially re-run
   (`--from-stage`/`--only-stage`) or fed pre-made inputs; the same planner drives `--dry-run`, so the dry run cannot disagree with a real run and impossible requests change nothing on disk.
3. **Made the system resilient to dying upstream APIs** (Google Custom Search shutdown, Reddit API gating, throttled free LLM models): fail-soft research collectors with wall-clock
   timeouts, a pluggable search-provider layer (swapped Google CSE for DuckDuckGo via config), and an LLM client with exponential backoff, `Retry-After` handling and model fallback.
4. **Engineered for testability without GPUs, network or secrets**: deterministic fakes for the LLM, TTS, avatar renderer and search fixtures give a full offline mode;
   401 tests (97 % branch coverage) run in ~10 s on Python 3.10/3.11, with a conftest guard that fails any test touching the network and real-ffmpeg end-to-end tests of the 1080×1920 output.
5. **Hardened secrets handling**: audited the repo and history with gitleaks, rotated a credential that had been committed and removed it from the tree (it remains in git history), and added a redaction layer (`scrub()` + logging filter) so API keys embedded in
   HTTP error URLs cannot reach logs, run metadata or terminal output; enforced by tests.
6. **Refactored a prototype into a packaged, typed project**: `src/` layout, pydantic config with YAML + env overrides, argparse CLI with `doctor`/`--dry-run`, ruff-clean code, lazy imports so
   the CLI and tests need no torch, GitHub Actions workflow (3.10/3.11), pre-commit and Makefile.
7. **Ran an AI-assisted cleanup with independent review loops**: parallel implementer agents on separate git worktrees, each change reviewed by a fresh reviewer that had not seen the
   implementer's reasoning; reviews caught real defects (stale-artifact resume bugs, a secret-leak path, a package-shadowing import bug) that were then fixed with regression tests.

## 30-second talk track

"It's a pipeline that takes a topic and produces a short vertical video with a talking avatar: it researches the topic, has an LLM write a narration, synthesizes speech, animates a
still image with SadTalker, and composites it over a looping background with ffmpeg. The interesting engineering is around it: every stage writes a file, so runs are resumable and
inspectable; the research layer tolerates dead services because two of the APIs I originally used were shut down or gated; and every heavy dependency has a fake, so the whole thing —
including real ffmpeg output — is built to run in CI without a GPU, network or keys. I turned a hard-coded prototype into a packaged project with a CLI, config, 400+ tests and a clean secrets story."

## What I'd do differently

* **Choose dependencies for compatibility first.** SadTalker's pins (numpy 1.23, torch 2.1) and the maintained Coqui fork cannot share an environment, which forces a two-virtualenv workflow. A newer talking-head model, or running each model behind its own small process/service, would avoid it.
* **Capture real-hardware runs as test fixtures early** (short recorded outputs of XTTS and SadTalker) so the mocked tests could assert against realistic data and the real stages could be smoke-tested in a scheduled job.
* **Design the stage interface before writing stages**: the unified `fn(..., cfg)` contract and the single planner were retrofitted, and so were captions (which need the script text in the compose stage).
* **Treat upstream APIs as unreliable from day one**: provider abstractions and offline fixtures were added after two services already broke.
* **Start with the test harness** (network guard, fakes, real-ffmpeg fixtures) instead of adding it after the code.
