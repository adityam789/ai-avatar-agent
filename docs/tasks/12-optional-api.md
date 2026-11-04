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

## Results (2026-11-03)
- `src/ai_avatar/api.py`: `POST /jobs {topic, offline?}` (202, id), `GET /jobs/{id}` (status, per-stage timings read from the run's `run.json`, scrubbed error, `video_ready`),
  `GET /jobs/{id}/video` (409 until done). One background worker thread (heavy stages are serial), in-memory job store (documented limitation), localhost default, no auth,
  topic length-limited. `pipeline.new_run_dir()` was added so the API knows the run directory (and thus live stage timings) before the run finishes.
- `ai-avatar serve --host --port` (lazy import: without the `api` extra it prints `pip install -e '.[api]'`). Importing the API does not import torch/TTS (tested in a subprocess).
- Tests (`tests/test_api.py`, 12 incl. parametrised): lifecycle + download, failed job with secret scrubbing, 404/409/422, per-job offline flag isolation, real worker thread, `serve` wiring.
  They `importorskip` fastapi/httpx; CI installs `.[dev,api]`.
- Verified for real (not only TestClient): started `ai-avatar serve`, POSTed an offline job over HTTP, polled to `done` (~4 s), downloaded a 1080x1920 h264/aac mp4.
- Not reviewed by an independent reviewer (optional stretch task; budget). Known: starlette emits a deprecation warning about `httpx` vs `httpx2` in TestClient.
