from models.sad_talker.inference import run
from pathlib import Path

def generate_avatar(audio_path, image_path, output_dir):
    run(driven_audio=audio_path,
        source_image=image_path,
        result_dir=output_dir,
        still=True,
        preprocess='full'
    )
    return sorted(Path(output_dir).glob("*.mp4"))[-1]