"""Compositing stage: stack the avatar video over a looping background clip with ffmpeg.

Both tiles are scaled to cover their area and centre-cropped (never stretched). The output length is
the avatar video's length (its audio track), so the endlessly looping background is simply cut off.
Burned-in captions are not implemented (``cfg.captions.enabled`` is currently ignored).
"""

from __future__ import annotations

import logging
import math
import shutil
import subprocess
from pathlib import Path

from ai_avatar.config import Config
from ai_avatar.errors import ComposeError
from ai_avatar.redact import scrub

log = logging.getLogger(__name__)

STDERR_TAIL_LINES = 12
OUTPUT_FPS = 25  # SadTalker renders at 25 fps; the background is resampled to match


def build_ffmpeg_cmd(
    avatar_video: Path,
    loop_video: Path,
    output_path: Path,
    *,
    duration: float,
    width: int,
    height: int,
    avatar_height: int,
    preset: str,
    crf: int,
) -> list[str]:
    """The ffmpeg argv that stacks ``avatar_video`` (``avatar_height`` px tall) over ``loop_video``.

    Pure: no I/O, so the exact command can be unit tested. ``duration`` (seconds) caps the output.
    """
    loop_height = height - avatar_height
    filter_complex = (
        f"[0:v]fps={OUTPUT_FPS},scale={width}:{avatar_height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{avatar_height}[top];"
        f"[1:v]fps={OUTPUT_FPS},scale={width}:{loop_height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{loop_height}[bottom];"
        "[top][bottom]vstack=inputs=2[v]"
    )
    return [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", str(avatar_video),
        "-stream_loop", "-1", "-i", str(loop_video),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-movflags", "+faststart",
        str(output_path),
    ]  # fmt: skip


def _tail(stderr: str) -> str:
    """The last few lines of a tool's stderr, scrubbed of secrets."""
    return scrub("\n".join(stderr.strip().splitlines()[-STDERR_TAIL_LINES:]))


def probe_duration(media: Path) -> float:
    """Container duration of ``media`` in seconds, via ffprobe (callers must check it is finite and positive)."""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(media)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    try:
        if result.returncode != 0:
            raise ValueError(f"ffprobe exited with status {result.returncode}")
        return float(result.stdout.strip())
    except ValueError as exc:
        raise ComposeError(
            f"Could not read the duration of {media} with ffprobe ({exc}); is it a valid media file?\n"
            f"{_tail(result.stderr)}"
        ) from exc


def compose(avatar_video: Path, loop_video: Path, output_path: Path, cfg: Config) -> None:
    """Write a ``cfg.video`` sized mp4: avatar on top, looping ``loop_video`` below, ending with the audio."""
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise ComposeError(
                f"{tool} not found on PATH. Install ffmpeg (macOS: brew install ffmpeg; Debian: apt install ffmpeg)."
            )
    for label, path in (("avatar video", avatar_video), ("background loop", loop_video)):
        if not path.is_file():
            raise ComposeError(f"The {label} does not exist: {path}")

    video = cfg.video
    avatar_height = int(video.height * cfg.avatar.height_ratio) // 2 * 2  # even, so yuv420p stays valid
    duration = probe_duration(avatar_video)
    if not (math.isfinite(duration) and duration > 0):
        raise ComposeError(f"The avatar video has no duration ({duration}): {avatar_video}")
    cmd = build_ffmpeg_cmd(
        avatar_video, loop_video, output_path,
        duration=duration, width=video.width, height=video.height, avatar_height=avatar_height,
        preset=video.preset, crf=video.crf,
    )  # fmt: skip

    log.info("Composing %.1fs video -> %s", duration, output_path)
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise ComposeError(f"ffmpeg exited with status {result.returncode}:\n{_tail(result.stderr)}")
