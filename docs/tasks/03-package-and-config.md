# 03 — Restructure into a proper package + config

## Goal
Clean `src`-style package, typed config, no hard-coded paths.

## Target layout
```
ai-avatar-agent/
  pyproject.toml
  README.md  CLAUDE.md  LICENSE  .env.example
  config/default.yaml
  src/ai_avatar/
    __init__.py  __main__.py  cli.py  config.py  pipeline.py  logging_setup.py
    research/ (collectors/, aggregator.py, cache.py, schemas.py, agent.py)
    llm/ (client.py)
    stages/ (script.py, tts.py, avatar.py, compose.py)
  tests/
  docs/
  assets/loops/        (see Task 11 for large files)
  models/sad_talker/   (submodule, untouched)
  run.py               (thin shim -> ai_avatar.cli.main, keep for back-compat)
```

## Steps
1. Use `git mv` to preserve history: `app/agents/research/*` -> `src/ai_avatar/research/`, `app/agents/{script,tts,avatar,composer}.py` -> `src/ai_avatar/stages/`, `llm_client.py` -> `llm/client.py`.
2. Fix imports (absolute `ai_avatar.*`). Remove duplicate/unused `app/__pycache__` noise; keep `.gitignore` handling it.
3. `config.py`: pydantic models (`VideoConfig`, `AvatarConfig`, `BackgroundConfig`, `LLMConfig`, `PathsConfig`) loaded from `config/default.yaml`, overridable by `--config` and env. Fields to include: output format/size (1080x1920), avatar height ratio, avatar image path, loop video path, tts voice/language/device, llm model list, outputs dir.
4. Move `app/config/video.yaml` content into `config/default.yaml`; make previously-unused keys (`format`, `brainrot.type`) actually used or delete them.
5. Resolve all paths relative to a project root (not CWD). Fix SadTalker's reliance on CWD by passing absolute `checkpoint_dir`/`result_dir` from our wrapper (do not edit the submodule unless unavoidable; if so, note it).
6. Delete the stale `__pycache__` directories from the working tree (they are ignored by git; ask before deleting anything else).

## Acceptance criteria
- `python -c "import ai_avatar"` works from any directory after `pip install -e .`.
- No string literal paths like `outputs/audio/<uuid>.wav` remain in code.
- `git log --follow` still shows history for moved files.
