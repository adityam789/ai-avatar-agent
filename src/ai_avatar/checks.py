"""Environment checks shared by ``--dry-run`` and ``doctor``. Never reports env-var values."""

import os
import shutil
from dataclasses import dataclass

from ai_avatar.config import Config

# Variable NAMES only; see .env.example. Value: (what it enables, required for a real run, secret).
ENV_VARS = {
    "OPEN_ROUTER_API_KEY": ("LLM calls", True, True),
    "OPEN_ROUTER_REFERER": ("OpenRouter attribution header", False, False),
    "OPEN_ROUTER_TITLE": ("OpenRouter attribution header", False, False),
    "GOOGLE_API_KEY": ("Google CSE web search (deprecated)", False, True),
    "GOOGLE_CSE_ID": ("Google CSE web search (deprecated)", False, False),
    "REDDIT_CLIENT_ID": ("Reddit collector", False, False),
    "REDDIT_CLIENT_SECRET": ("Reddit collector", False, True),
    "REDDIT_USER_AGENT": ("Reddit collector", False, False),
}


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True  # optional checks are reported but never fail a dry run


def check_environment(cfg: Config) -> list[Check]:
    """Static checks for a real run: binaries, input files, model checkpoints, env var names."""
    checks = [
        Check("ffmpeg", shutil.which("ffmpeg") is not None, shutil.which("ffmpeg") or "not on PATH"),
        Check("ffprobe", shutil.which("ffprobe") is not None, shutil.which("ffprobe") or "not on PATH"),
    ]
    image = cfg.resolve(cfg.avatar.image)
    checks.append(Check("avatar image", image.is_file(), str(image)))
    if cfg.background.enabled:
        loop = cfg.resolve(cfg.background.loop)
        checks.append(Check("background loop", loop.is_file(), str(loop)))
    ckpt = cfg.sadtalker_checkpoints
    checks.append(
        Check("SadTalker checkpoints", ckpt.is_dir(), str(ckpt) + ("" if ckpt.is_dir() else " (download weights with models/sad_talker/scripts/download_models.sh)"))
    )
    for name, (purpose, required, _secret) in ENV_VARS.items():
        is_set = bool(os.getenv(name))
        checks.append(Check(f"env {name}", is_set, f"{'set' if is_set else 'unset'} - {purpose}", required))
    return checks
