# 02 — Packaging, dependencies, Python version

## Goal
`pip install -e .` works from a fresh venv; dependencies are honest, split, and current enough.

## Context
- `requirements.txt` pins torch 2.1.2 / transformers 4.36.2, lists `praw` twice, includes unused `fastapi/uvicorn/pydantic`, and uses the unmaintained `TTS` package.
- `.pyc` files show Python 3.10 and 3.14 used. Torch 2.1 + SadTalker realistically need **3.10**.
- Maintained Coqui fork: PyPI `coqui-tts` (Idiap). Import path remains `from TTS.api import TTS`.

## Steps
1. Decide target Python: 3.10 (document in README + `.python-version`). Verify by checking what `.venv` uses.
2. Create `pyproject.toml` (setuptools or hatchling) with project name `ai-avatar-agent`, package `ai_avatar` (see Task 03), console script `ai-avatar = ai_avatar.cli:main`.
3. Split deps: core (`requests`, `pyyaml`, `python-dotenv`, `feedparser`, `pydantic`), extras: `[tts]` (`coqui-tts`), `[avatar]` (torch/torchvision/torchaudio, face-alignment, librosa, scikit-image, opencv-python, imageio, imageio-ffmpeg, safetensors, etc. — mirror SadTalker's requirements), `[reddit]` (`praw`), `[dev]` (`pytest`, `pytest-cov`, `ruff`, `mypy` optional), `[api]` (`fastapi`, `uvicorn`).
4. `pyyaml` is used by the orchestrator but missing from requirements — add it.
5. Keep a `requirements.txt` that simply does `-e .[tts,avatar,reddit]` for people who expect it, or delete it and update docs. Pick one, document it.
6. Make heavy imports lazy so `import ai_avatar` and `--help` work without torch/TTS installed.
7. Do NOT upgrade torch/transformers blindly: record in `docs/KNOWN_ISSUES.md` that pins are intentionally old for SadTalker compatibility, and note what an upgrade would require.

## Acceptance criteria
- Fresh venv: `pip install -e ".[dev]"` succeeds quickly (no torch) and `pytest` can run.
- `pip install -e ".[tts,avatar]"` documented and verified to at least resolve (`pip install --dry-run`).
- No duplicate/unused deps.

## Open questions
- Is the owner's machine Apple Silicon (MPS) or CUDA? Note device handling in Task 08.
