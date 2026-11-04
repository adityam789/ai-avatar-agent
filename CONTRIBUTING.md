# Contributing

This project is in maintenance mode, but fixes are welcome.

```bash
python3.10 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install          # optional: ruff, whitespace, detect-secrets
make lint test              # ruff check + format --check, then pytest with coverage
```

* Tests must pass offline: no GPU, network, model downloads or real secrets. Mock external services or use the fakes (`--offline` mode); mark anything that truly needs them `@pytest.mark.integration` (skipped by default).
* Never commit `.env`, media outputs or model weights. Only variable *names* belong in `.env.example`.
* Route text derived from exceptions through `ai_avatar.redact.scrub` before logging or storing it.
* Do not edit the `models/sad_talker` submodule; work around it in `stages/avatar.py`.
* Keep changes small and readable; add a test for every behaviour you change.
