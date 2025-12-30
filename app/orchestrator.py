from pathlib import Path
import yaml

# Use package-relative imports so this module works whether imported as
# `app.orchestrator` or executed within the package context.
from .agents.script import generate_script
from .agents.tts import generate_audio
from .agents.avatar import generate_avatar
from .agents.composer import compose

CONFIG_PATH = Path("app/config/video.yaml")

def run(topic: str):
    config = yaml.safe_load(CONFIG_PATH.read_text())

    # script = generate_script(topic)
    # print("Generated script:", script)
    # audio = generate_audio(script)
    # print("Generated audio at:", audio)

    avatar_video = generate_avatar(
        audio_path="outputs/audio/087faadb-676b-4e70-925c-1244cd167e62.wav",
        image_path="models/sad_talker/examples/source_image/full_body_1.png",
        output_dir="outputs/video"
    )

    final_path = Path("outputs/final/final.mp4")
    final_path.parent.mkdir(parents=True, exist_ok=True)

    if config["brainrot"]["enabled"]:
        compose(
            avatar_video=avatar_video,
            loop_video=Path("assets/loops/china_surfer_low.mp4"),
            output_path=final_path,
            avatar_ratio=config["avatar"]["height_ratio"]
        )
    else:
        avatar_video.rename(final_path)

    return final_path
