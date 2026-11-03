# 12 — (Optional stretch) FastAPI service

Only do this if everything else is done. `fastapi`, `uvicorn`, `pydantic` were already in the original requirements and a stale `main.cpython-*.pyc` suggests an `app/main.py` once existed.

## Goal
Tiny HTTP wrapper demonstrating the pipeline as a service.

## Steps
1. `src/ai_avatar/api.py`: `POST /jobs {topic}` -> returns job id; background task runs `pipeline.run`; `GET /jobs/{id}` -> status + stage timings; `GET /jobs/{id}/video` -> file. In-memory job store is fine (document the limitation).
2. `ai-avatar serve --host --port` command; `[api]` extra.
3. Tests with FastAPI `TestClient` using fake stages.
4. README section + a curl example.

## Acceptance criteria
- `ai-avatar serve` boots without torch installed (heavy imports stay lazy).
- Tests pass offline.
