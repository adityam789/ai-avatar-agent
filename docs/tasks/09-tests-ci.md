# 09 — Tests, lint, CI

## Goal
Green, fast CI that needs no GPU, network, or secrets.

## Steps
1. `tests/` with pytest. Mark anything slow/external with `@pytest.mark.integration` and skip by default.
2. Cover: config loading/validation, research (collectors with mocked HTTP, aggregator JSON parsing, cache TTL), LLM client (retry/fallback), script word budget/sanitizer, compose cmd builder, pipeline orchestration with fake stages (+ resume), CLI smoke (`--help`, `doctor`, `--dry-run`).
3. Use `responses` or `requests-mock` (or `monkeypatch`) — no real HTTP. Add `conftest.py` that fails tests attempting network access (e.g. patch `socket.socket.connect`).
4. Lint/format: `ruff` (`ruff check`, `ruff format`) configured in `pyproject.toml`; optional `mypy --strict` on `config.py`, `pipeline.py`, `llm/`. Don't boil the ocean.
5. `.github/workflows/ci.yml`: matrix Python 3.10 (and 3.11 if it passes), steps: checkout (no submodules needed), setup-python, `pip install -e ".[dev]"`, `ruff check`, `ruff format --check`, `pytest -q --cov=ai_avatar`. Add a status badge to README.
6. Optional `pre-commit` config (ruff + end-of-file-fixer + detect-secrets).
7. Optional `Makefile` / `justfile`: `make install test lint demo doctor`.

## Acceptance criteria
- `pytest` passes locally in < 30s with no extras installed beyond `[dev]`.
- CI workflow file present and valid YAML; (owner pushes to see it go green).
- Coverage ≥ 70% on `src/ai_avatar` excluding stages that require heavy models.

## Results (2026-11-03)
- Tests: 401 passing in ~8 s with only `.[dev]` installed (no torch/TTS), on Python 3.10 and 3.11 (both run locally). Integration-marked tests
  are skipped by default (`addopts = -m 'not integration'`); there are currently none left that need credentials.
- `tests/conftest.py` fails any test that opens a non-loopback socket (subprocess ffmpeg is unaffected).
- Coverage 97% (branch) on `src/ai_avatar` (`pytest --cov=ai_avatar`); target was >= 70%. Lowest: `__main__.py` (3 lines, covered by a subprocess test),
  `checks.py` 83% (real-torch branch).
- Lint/format: `ruff check .` and `ruff format --check .` clean (rules E,F,I,W,UP,B,SIM; line length 120; submodule/gfpgan/outputs excluded).
  One per-file ignore (W291 in `tests/test_llm_fake.py`: trailing spaces in a prompt fixture are the point of the test).
- CI: `.github/workflows/ci.yml` (3.10 + 3.11 matrix, installs ffmpeg, ruff check, ruff format --check, pytest --cov). **Not run on GitHub** — the owner
  pushes to see it go green. YAML validated locally. Optional: `.pre-commit-config.yaml` (ruff, whitespace, detect-secrets) and `Makefile`
  (`install test lint format doctor demo`).
- mypy: skipped (optional in the task).
- Also fixed (from Task 08 review nits): TTS now deletes a partial wav when synthesis raises; stale "(Task NN)" comments removed from `config.py`.
- README badge is added in Task 10.
