"""Helpers that generate tiny media files with the real ffmpeg (for tests that need it)."""

import shutil
import subprocess
from pathlib import Path

import pytest

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe not installed"
)


def _ffmpeg(*args: object) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *map(str, args)], check=True)


def make_video(path: Path, seconds: float = 1.0, size: str = "160x160", fps: int = 10, audio: bool = False) -> Path:
    """A test-pattern mp4 (h264, yuv420p), optionally with a sine-wave aac track."""
    args = ["-f", "lavfi", "-i", f"testsrc=size={size}:rate={fps}:duration={seconds}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=16000:duration={seconds}"]
    audio_args = ["-c:a", "aac"] if audio else []
    _ffmpeg(*args, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", *audio_args, path)
    return path


def make_image(path: Path, size: str = "120x200") -> Path:
    _ffmpeg("-f", "lavfi", "-i", f"testsrc=size={size}:rate=1", "-frames:v", "1", path)
    return path


def probe(path: Path) -> dict:
    """Stream/duration facts from ffprobe: ``{"video": {...}, "audio": {...} | None, "duration": float}``."""
    import json

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout  # fmt: skip
    data = json.loads(out)
    streams = {s["codec_type"]: s for s in data["streams"]}
    return {"video": streams["video"], "audio": streams.get("audio"), "duration": float(data["format"]["duration"])}
