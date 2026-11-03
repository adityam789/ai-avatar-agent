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
