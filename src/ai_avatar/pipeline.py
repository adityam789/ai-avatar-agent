"""Pipeline: topic -> script -> speech -> talking head -> composited vertical video.

Task 04 replaces this with a staged, resumable runner; for now it wires the stages
together using only paths from :class:`ai_avatar.config.Config`.
"""

import shutil
import uuid
from pathlib import Path

from ai_avatar.config import Config, load_config
from ai_avatar.stages.avatar import generate_avatar
from ai_avatar.stages.compose import compose
from ai_avatar.stages.script import generate_script
from ai_avatar.stages.tts import generate_audio


def run(topic: str, cfg: Config | None = None) -> Path:
    """Generate a video about ``topic`` and return the path of the final mp4."""
    cfg = cfg or load_config()
    out = cfg.outputs_dir
    run_id = uuid.uuid4().hex[:8]

    script = generate_script(topic)
    audio = generate_audio(script, out / "audio" / f"{run_id}.wav", cfg.tts)
    avatar_video = generate_avatar(audio, cfg.resolve(cfg.avatar.image), out / "video" / run_id, cfg)

    final_path = out / "final" / f"{run_id}.mp4"
    final_path.parent.mkdir(parents=True, exist_ok=True)

    if cfg.background.enabled:
        compose(
            avatar_video=avatar_video,
            loop_video=cfg.resolve(cfg.background.loop),
            output_path=final_path,
            avatar_ratio=cfg.avatar.height_ratio,
            width=cfg.video.width,
            height=cfg.video.height,
        )
    else:
        shutil.copyfile(avatar_video, final_path)

    return final_path
