"""Offline stand-ins for the heavy stages (used when ``cfg.offline`` is set, and in tests).

Both mimic the call signature of the real backend they replace (``TTS.tts_to_file`` and SadTalker's
``run``), so the real wrapper code around them -- validation, output detection -- is exercised too.
No model, GPU or network is involved; the avatar fake does need a real ``ffmpeg``.
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path
from time import strftime

from ai_avatar.errors import AvatarError

WORDS_PER_SECOND = 2.5  # same rule of thumb as the script length target
MIN_SECONDS = 0.5
SAMPLE_RATE = 16000


class FakeTTS:
    """Writes silence whose length is proportional to the text (about 2.5 words per second)."""

    def tts_to_file(self, text: str, file_path: str, **_voice_options: str) -> None:
        seconds = max(MIN_SECONDS, len(text.split()) / WORDS_PER_SECOND)
        with wave.open(file_path, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(SAMPLE_RATE)
            f.writeframes(b"\x00\x00" * int(SAMPLE_RATE * seconds))


class FakeAvatar:
    """Renders the still image plus the audio into an mp4, named like SadTalker's output."""

    def run(self, driven_audio: str, source_image: str, result_dir: str, size: int = 256, **_options: object) -> None:
        if shutil.which("ffmpeg") is None:
            raise AvatarError("The offline avatar needs ffmpeg on PATH (macOS: brew install ffmpeg).")
        out = Path(result_dir) / f"{strftime('%Y_%m_%d_%H.%M.%S')}.mp4"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-framerate", "25", "-i", source_image,
            "-i", driven_audio,
            "-vf", f"scale={size}:{size}:force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(out),
        ]  # fmt: skip
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise AvatarError(f"ffmpeg could not render the offline avatar: {result.stderr.strip()[-500:]}")
