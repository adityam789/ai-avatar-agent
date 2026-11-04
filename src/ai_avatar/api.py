"""Tiny HTTP wrapper around the pipeline (optional ``api`` extra: ``pip install -e '.[api]'``).

* ``POST /jobs {"topic": "...", "offline": false}`` -> ``202 {"id": ...}``; the run happens in a background worker
* ``GET /jobs/{id}`` -> status, per-stage timings (from the run's ``run.json``) and, on failure, a scrubbed error
* ``GET /jobs/{id}/video`` -> the finished ``final.mp4``

Limitations (this is a demo, not a production service): jobs live in memory and vanish on restart; one job runs at a
time (the heavy stages are GPU/CPU bound); there is no authentication, so bind it to localhost (the default).
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import uuid
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ai_avatar import pipeline
from ai_avatar.config import Config, load_config
from ai_avatar.redact import scrub

log = logging.getLogger(__name__)


class JobRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    offline: bool = False  # fixtures + fake LLM/TTS/avatar


@dataclass
class Job:
    id: str
    topic: str
    run_dir: Path
    status: str = "queued"  # queued | running | done | failed
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def video(self) -> Path:
        return self.run_dir / "final.mp4"


def create_app(
    cfg: Config | None = None,
    stages: tuple[pipeline.Stage, ...] = pipeline.DEFAULT_STAGES,
    executor: Executor | None = None,
) -> FastAPI:
    """Build the app. ``stages`` and ``executor`` are injectable so tests run synchronously with fake stages."""
    base_cfg = cfg or load_config()
    pool = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-avatar-job")
    jobs: dict[str, Job] = {}
    lock = threading.Lock()
    app = FastAPI(title="ai-avatar-agent", version="0.1.0")

    def work(job: Job, job_cfg: Config) -> None:
        with lock:
            job.status = "running"
        try:
            pipeline.run(job.topic, job_cfg, resume=job.run_dir, stages=stages)
            outcome, error = "done", None
        except Exception as exc:  # noqa: BLE001 - any failure becomes a failed job, never a crashed worker
            log.warning("job %s failed: %s", job.id, scrub(exc))
            outcome, error = "failed", f"{type(exc).__name__}: {scrub(exc)}"
        with lock:
            job.status, job.error = outcome, error

    @app.post("/jobs", status_code=202)
    def create_job(request: JobRequest) -> dict:
        job_cfg: Config = base_cfg.model_copy(deep=True)
        job_cfg.offline = request.offline or base_cfg.offline
        job = Job(id=uuid.uuid4().hex[:12], topic=request.topic, run_dir=pipeline.new_run_dir(request.topic, job_cfg))
        with lock:
            jobs[job.id] = job
        pool.submit(work, job, job_cfg)
        return {"id": job.id, "status": job.status}

    def get_job(job_id: str) -> Job:
        with lock:
            job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job id")
        return job

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        job = get_job(job_id)
        record: dict = {}
        run_json = job.run_dir / "run.json"
        if run_json.is_file():
            with contextlib.suppress(OSError, json.JSONDecodeError):  # mid-write: the next poll will see it
                record = json.loads(run_json.read_text())
        return {
            "id": job.id,
            "topic": job.topic,
            "status": job.status,
            "error": job.error,
            "created_at": job.created_at,
            "stages": record.get("stages", {}),
            "video_ready": job.status == "done" and job.video.is_file(),
        }

    @app.get("/jobs/{job_id}/video")
    def job_video(job_id: str) -> FileResponse:
        job = get_job(job_id)
        if job.status != "done" or not job.video.is_file():
            raise HTTPException(status_code=409, detail=f"video not ready (job is {job.status})")
        return FileResponse(job.video, media_type="video/mp4", filename=f"{job.id}.mp4")

    return app


def serve(host: str = "127.0.0.1", port: int = 8000, cfg: Config | None = None) -> None:
    """Run the API with uvicorn (blocking)."""
    import uvicorn

    uvicorn.run(create_app(cfg), host=host, port=port)


__all__ = ["Job", "JobRequest", "create_app", "serve"]
