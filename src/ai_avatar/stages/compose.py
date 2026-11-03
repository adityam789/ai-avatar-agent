"""Compositing stage: stack the avatar video over a looping background clip with ffmpeg."""

import subprocess
from pathlib import Path

def compose(
    avatar_video: Path,
    loop_video: Path,
    output_path: Path,
    avatar_ratio=0.55,
    width=1080,
    height=1920
):
    """Write a ``width`` x ``height`` video: avatar on top, looping ``loop_video`` below."""
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
