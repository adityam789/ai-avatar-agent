import uuid
from functools import lru_cache
from pathlib import Path

AUDIO_DIR = Path("outputs/audio")
LANGUAGE = "en"


@lru_cache(maxsize=1)
def _get_tts():
    """Load XTTS v2 on first use so importing this module needs no TTS install."""
    from TTS.api import TTS  # heavy; requires the `tts` extra

    return TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=False)


def generate_audio(script: str) -> str:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}.wav"
    output_path = AUDIO_DIR / filename
    # generate speech by cloning a voice using default settings
    _get_tts().tts_to_file(
        text=script,
        file_path=output_path,
        speaker = "Ana Florence",
        language=LANGUAGE
    )
    return str(output_path)


