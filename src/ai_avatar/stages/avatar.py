"""Talking-head stage: drives a still image with audio using SadTalker (git submodule)."""

import logging
import sys
from contextlib import contextmanager
from pathlib import Path

from ai_avatar.config import Config
from ai_avatar.errors import AvatarError

log = logging.getLogger(__name__)


@contextmanager
def _sadtalker_context(cfg: Config):
    """Make the SadTalker submodule importable and independent of the CWD.

    * The project root goes on ``sys.path`` so ``models.sad_talker.inference`` imports.
    * The submodule dir goes first so SadTalker's own ``src`` package wins over this
      repo's ``src/`` directory (which would otherwise import as an empty namespace package).
    * ``inference.py`` builds its config path from ``sys.argv[0]``, so we point ``argv[0]``
      at the project root for the call instead of editing the submodule.

    Everything is restored on exit, including when SadTalker raises.
    """
    entries = [str(cfg.sadtalker_dir), str(cfg.root)]  # inserted so sadtalker_dir ends up first
    saved_argv0 = sys.argv[0]
    for entry in reversed(entries):
        sys.path.insert(0, entry)
    sys.argv[0] = str(cfg.root / "ai-avatar")
    try:
        yield
    finally:
        sys.argv[0] = saved_argv0
        for entry in entries:
            sys.path.remove(entry)


def generate_avatar(audio_path: Path, image_path: Path, result_dir: Path, cfg: Config) -> Path:
    """Render the talking-head video into ``result_dir`` and return its path."""
    result_dir.mkdir(parents=True, exist_ok=True)
    before = {p: p.stat().st_mtime_ns for p in result_dir.glob("*.mp4")}
    checkpoints = cfg.sadtalker_checkpoints
    with _sadtalker_context(cfg):
        from models.sad_talker.inference import run  # heavy; requires the `avatar` extra

        run(
            driven_audio=str(audio_path),
            source_image=str(image_path),
            result_dir=str(result_dir),
            checkpoint_dir=str(checkpoints),
            bfm_folder=str(checkpoints / "BFM_Fitting"),
            still=True,
            preprocess="full",
        )
    new = sorted(
        (p for p in result_dir.glob("*.mp4") if before.get(p) != p.stat().st_mtime_ns),
        key=lambda p: p.stat().st_mtime_ns,
    )
    if not new:
        raise AvatarError(f"SadTalker finished but wrote no new .mp4 to {result_dir}")
    if len(new) > 1:
        log.warning("SadTalker wrote %d videos to %s; using the newest: %s", len(new), result_dir, new[-1].name)
    return new[-1]
