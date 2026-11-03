"""Compositing stage: stack the avatar video over a looping background clip with ffmpeg."""

import subprocess
from pathlib import Path

from ai_avatar.config import Config


def compose(avatar_video: Path, loop_video: Path, output_path: Path, cfg: Config) -> None:
    """Write a ``cfg.video`` sized video: avatar on top, looping ``loop_video`` below."""
    avatar_ratio, width, height = cfg.avatar.height_ratio, cfg.video.width, cfg.video.height
    avatar_h = int(height * avatar_ratio)
    loop_h = height - avatar_h

    filter_complex = (
        f"[0:v]scale={width}:{avatar_h}[top];"
        f"[1:v]scale={width}:{loop_h},crop={width}:{loop_h}[bottom];"
        f"[top][bottom]vstack=inputs=2[v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(avatar_video),
        "-stream_loop", "-1",
        "-i", str(loop_video),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "0:a?",
        "-shortest",
        str(output_path)
    ]

    subprocess.run(cmd, check=True)
