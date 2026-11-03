"""Text-to-speech stage using Coqui XTTS v2 (``coqui-tts`` package, ``tts`` extra).

XTTS v2 weights are under the Coqui Public Model License (non-commercial use).
"""

from functools import lru_cache
from pathlib import Path

from ai_avatar.config import TTSConfig


@lru_cache(maxsize=1)
def _get_tts(use_gpu: bool):
    """Load XTTS v2 on first use so importing this module needs no TTS install."""
    from TTS.api import TTS  # heavy; requires the `tts` extra

    return TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=use_gpu)


def generate_audio(script: str, output_path: Path, cfg: TTSConfig) -> Path:
    """Synthesize ``script`` to ``output_path`` (wav) and return that path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _get_tts(cfg.device == "cuda").tts_to_file(
        text=script,
        file_path=str(output_path),
        speaker=cfg.voice,
        language=cfg.language,
    )
    return output_path
