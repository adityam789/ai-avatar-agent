"""Environment checks shared by ``--dry-run`` and ``doctor``. Never reports env-var values."""

import importlib.util
import os
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

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
    """Static checks: binaries, input files, model checkpoints, env var names.

    With ``cfg.offline`` the checkpoints and API keys are reported but not required (the fakes need
    neither); ffmpeg and ffprobe still are, and so are the avatar image and background loop for the
    stages that read them (the CLI dry run decides which stages those are).
    """
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
    hint = "" if ckpt.is_dir() else " (download weights with models/sad_talker/scripts/download_models.sh)"
    checks.append(Check("SadTalker checkpoints", ckpt.is_dir(), str(ckpt) + hint, required=not cfg.offline))
    for name, (purpose, required, _secret) in ENV_VARS.items():
        is_set = bool(os.getenv(name))
        checks.append(
            Check(f"env {name}", is_set, f"{'set' if is_set else 'unset'} - {purpose}", required and not cfg.offline)
        )
    return checks


# Checks whose failure makes `ai-avatar doctor` exit non-zero: nothing runs without them.
# Everything else (torch, TTS, checkpoints, API keys) is reported but only matters for a real,
# non-offline run.
CORE_CHECKS = {"python", "ffmpeg", "ffprobe"}
# Optional installs that a real (non-offline) run cannot do without.
REAL_RUN_CHECKS = {"torch", "TTS package"}


def _xtts_cache_candidates() -> list[Path]:
    name = "tts_models--multilingual--multi-dataset--xtts_v2"
    bases = [Path(os.environ["TTS_HOME"]) / "tts"] if os.getenv("TTS_HOME") else []
    if os.getenv("XDG_DATA_HOME"):
        bases.append(Path(os.environ["XDG_DATA_HOME"]) / "tts")
    bases += [Path.home() / ".local/share/tts", Path.home() / "Library/Application Support/tts"]
    return [base / name for base in bases]


def check_runtime() -> list[Check]:
    """Interpreter and optional heavy dependencies. Imports torch only if it is installed."""
    py = sys.version_info
    checks = [
        Check(
            "python",
            (3, 10) <= py[:2] < (3, 12),
            f"{platform.python_version()} (supported: 3.10-3.11; 3.10 recommended)",
        )
    ]
    if importlib.util.find_spec("torch") is None:
        checks.append(Check("torch", False, "not installed - needed for a real run: pip install -e '.[avatar]'", False))
    else:
        try:
            import torch

            if torch.cuda.is_available():
                device = "cuda"
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu only"
            checks.append(Check("torch", True, f"{torch.__version__} ({device})", False))
        except Exception as exc:  # broken wheel, missing CUDA libs, ...
            checks.append(Check("torch", False, f"installed but fails to import: {type(exc).__name__}: {exc}", False))
    tts_installed = importlib.util.find_spec("TTS") is not None
    checks.append(
        Check(
            "TTS package",
            tts_installed,
            "installed" if tts_installed else "not installed: pip install -e '.[tts]'",
            False,
        )
    )
    cached = next((p for p in _xtts_cache_candidates() if p.is_dir()), None)
    checks.append(
        Check(
            "XTTS v2 model",
            cached is not None,
            str(cached) if cached else "not cached (downloaded on first real run, ~2 GB)",
            False,
        )
    )
    praw_installed = importlib.util.find_spec("praw") is not None
    checks.append(
        Check(
            "praw (Reddit)",
            praw_installed,
            "installed" if praw_installed else "optional: pip install -e '.[reddit]'",
            False,
        )
    )
    return checks
