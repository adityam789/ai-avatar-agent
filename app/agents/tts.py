import uuid
from pathlib import Path
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=False)

AUDIO_DIR = Path("outputs/audio")
LANGUAGE = "en"

def generate_audio(script: str) -> str:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}.wav"
    output_path = AUDIO_DIR / filename
    # generate speech by cloning a voice using default settings
    tts.tts_to_file(
        text=script,
        file_path=output_path,
        speaker = "Ana Florence",
        language=LANGUAGE
    )
    return str(output_path)


