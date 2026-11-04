# CLAUDE.md — ai-avatar-agent

## Goal of the current work
This project is being **wrapped up as a polished portfolio piece** (resume / GitHub showcase). It is fine for it to be
"retired": some upstream services (Reddit API, Google Custom Search) are shutting down or restricted. The goal is a clean,
well-documented, well-structured, testable repo — not new features.

Work through the task files in `docs/tasks/` **in numeric order**. Start with `docs/tasks/README.md`.

## What the project does
Topic -> research (Reddit + Google CSE + RSS) -> LLM script (OpenRouter) -> TTS (Coqui XTTS v2) -> talking-head avatar
(SadTalker, git submodule) -> ffmpeg composite (avatar stacked over looping gameplay clip) -> vertical 1080x1920 mp4.

## Current layout (before refactor)
- `run.py` entry point; `app/orchestrator.py` sequences stages (currently HARD-CODED audio/image paths, script+TTS commented out)
- `app/agents/{script,tts,avatar,composer,llm_client}.py`
- `app/agents/research/` collectors (`reddit`, `google_cse`, `rss`), `aggregator.py`, `cache.py` (in-memory), `schemas.py`
- `app/config/video.yaml`
- `models/sad_talker/` = git submodule (fork: github.com/adityam789/SadTalker; adds programmatic `run()` in inference.py)
- `outputs/`, `gfpgan/`, `.venv/` are gitignored. Model checkpoints live under `models/sad_talker/checkpoints` (large, local only).

## Hard rules
1. **Never print, log, commit, or copy values from `.env`.** Only reference variable names. Maintain `.env.example` with names only.
2. `test_research.py` contains hard-coded Reddit credentials (already in git history). Task 01 handles this — do not re-add secrets anywhere.
3. Do not delete user files (outputs, checkpoints, assets) or rewrite git history without asking. Propose, then wait.
4. Do not modify files inside `models/sad_talker/` unless a task says so; it is a submodule with its own repo.
5. No GPU/network/model downloads in tests. Everything external must be mockable.
6. Keep each task as its own commit with a clear message. Run lint + tests before committing once Task 09 exists.
7. Prefer small, readable code over clever abstractions. This repo is a showcase: clarity counts.
8. When a task needs a decision from the owner (Aditya), write it under "Open questions" in that task file and move on.

## Known external-service status (as of Nov 2026)
- Google Custom Search JSON API: closed to new customers; discontinued 2027-01-01.
- Reddit Data API: requires approval (Responsible Builder Policy); new requests reportedly closed Oct 31 2026.
- OpenRouter `:free` models rotate/throttle without notice -> need fallbacks.
- XTTS v2 weights: Coqui Public Model License (non-commercial). Maintained package is `coqui-tts` (Idiap fork), not `TTS`.
- SadTalker: Apache-2.0 code; pretrained weights/third-party components have their own terms — document in README.

## Definition of done for the whole effort
Fresh clone -> `pip install -e .` -> `python -m ai_avatar --help` works; `pytest` passes without GPU/network; CI green;
README has architecture diagram, demo, quickstart, limitations/status; no secrets in tree; repo size sane.
