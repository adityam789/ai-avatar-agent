"""HTTP API tests: FastAPI TestClient with fake stages and a synchronous executor (no threads, no heavy deps)."""

import json
import subprocess
import sys
import time
from concurrent.futures import Executor, Future

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from ai_avatar import cli  # noqa: E402
from ai_avatar.api import create_app  # noqa: E402
from ai_avatar.config import load_config  # noqa: E402
from ai_avatar.errors import TTSError  # noqa: E402
from ai_avatar.pipeline import Stage  # noqa: E402


class InlineExecutor(Executor):
    """Runs submitted work immediately, in the caller's thread."""

    def submit(self, fn, /, *args, **kwargs):
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001
            future.set_exception(exc)
        return future


def fake_stages(fail_at: str | None = None):
    def make(name, artifact, requires=None):
        def fn(ctx):
            if name == fail_at:
                raise RuntimeError("boom sk-or-v1-abcdef123456")
            ctx.path(artifact).write_text(f"{name}:{ctx.topic}")

        return Stage(name, artifact, fn, TTSError, requires)

    return (
        make("research", "research.json"),
        make("script", "script.txt", "research.json"),
        make("tts", "audio.wav", "script.txt"),
        make("avatar", "avatar.mp4", "audio.wav"),
        make("compose", "final.mp4", "avatar.mp4"),
    )


@pytest.fixture
def make_client(tmp_path):
    cfg = load_config(environ={"AI_AVATAR__paths__outputs_dir": str(tmp_path / "out")})

    def make(**kwargs):
        return TestClient(create_app(cfg, executor=InlineExecutor(), **kwargs))

    return make


def test_job_lifecycle_and_video_download(make_client):
    client = make_client(stages=fake_stages())
    created = client.post("/jobs", json={"topic": "black holes"})
    assert created.status_code == 202
    job_id = created.json()["id"]

    status = client.get(f"/jobs/{job_id}").json()
    assert status["status"] == "done" and status["topic"] == "black holes" and status["error"] is None
    assert set(status["stages"]) == {"research", "script", "tts", "avatar", "compose"}
    assert all(s["status"] == "done" and "seconds" in s for s in status["stages"].values())
    assert status["video_ready"] is True

    video = client.get(f"/jobs/{job_id}/video")
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4"
    assert video.content == b"compose:black holes"


def test_failed_job_reports_a_scrubbed_error_and_has_no_video(make_client, monkeypatch):
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-or-v1-abcdef123456")
    client = make_client(stages=fake_stages(fail_at="tts"))
    job_id = client.post("/jobs", json={"topic": "x"}).json()["id"]

    status = client.get(f"/jobs/{job_id}").json()
    assert status["status"] == "failed" and "tts stage failed" in status["error"]
    assert "abcdef123456" not in json.dumps(status)  # secrets never leave through the API
    assert status["stages"]["tts"]["status"] == "failed"
    assert client.get(f"/jobs/{job_id}/video").status_code == 409


def test_unknown_job_is_404(make_client):
    client = make_client(stages=fake_stages())
    assert client.get("/jobs/nope").status_code == 404
    assert client.get("/jobs/nope/video").status_code == 404


@pytest.mark.parametrize("body", [{}, {"topic": ""}, {"topic": "x" * 201}, {"topic": 5}])
def test_invalid_requests_are_422(make_client, body):
    assert make_client(stages=fake_stages()).post("/jobs", json=body).status_code == 422


def test_video_not_ready_while_running(make_client):
    class NeverRuns(Executor):
        def submit(self, fn, /, *args, **kwargs):
            return Future()  # the job stays queued

    cfg = load_config(environ={})
    client = TestClient(create_app(cfg, stages=fake_stages(), executor=NeverRuns()))
    job_id = client.post("/jobs", json={"topic": "x"}).json()["id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "queued"
    assert client.get(f"/jobs/{job_id}/video").status_code == 409


def test_offline_flag_is_applied_per_job(make_client, monkeypatch):
    seen = []

    def spy(topic, cfg, **kwargs):
        seen.append(cfg.offline)
        (kwargs["resume"] / "final.mp4").write_bytes(b"v")

    monkeypatch.setattr("ai_avatar.api.pipeline.run", spy)
    client = make_client(stages=fake_stages())
    client.post("/jobs", json={"topic": "a", "offline": True})
    client.post("/jobs", json={"topic": "b"})
    assert seen == [True, False]  # one job's flag must not leak into the next


def test_real_thread_pool_runs_jobs_in_the_background(tmp_path):
    cfg = load_config(environ={"AI_AVATAR__paths__outputs_dir": str(tmp_path / "out")})
    client = TestClient(create_app(cfg, stages=fake_stages()))  # default executor: a real worker thread
    job_id = client.post("/jobs", json={"topic": "threads"}).json()["id"]
    deadline = time.time() + 10
    while time.time() < deadline and client.get(f"/jobs/{job_id}").json()["status"] not in ("done", "failed"):
        time.sleep(0.05)
    assert client.get(f"/jobs/{job_id}").json()["status"] == "done"


def test_serve_command_boots_the_app_without_heavy_deps(monkeypatch):
    started = {}
    monkeypatch.setattr("ai_avatar.api.serve", lambda host, port, cfg: started.update(host=host, port=port))
    assert cli.main(["serve", "--port", "8123"]) == 0
    assert started == {"host": "127.0.0.1", "port": 8123}


def test_serve_without_the_api_extra_gives_an_install_hint(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "ai_avatar.api", None)  # makes `from ai_avatar import api` raise ImportError
    assert cli.main(["serve"]) == 1
    assert "pip install -e '.[api]'" in capsys.readouterr().err


def test_importing_the_api_does_not_import_torch_or_tts():
    code = "import sys, ai_avatar.api; print('torch' in sys.modules, 'TTS' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.split() == ["False", "False"]
