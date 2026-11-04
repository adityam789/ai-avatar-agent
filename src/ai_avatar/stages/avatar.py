"""Talking-head stage: drives a still image with audio using SadTalker (git submodule).

SadTalker (Apache-2.0 code; its pretrained weights have their own terms) is imported lazily from
``models/sad_talker``. With ``cfg.offline`` a :class:`~ai_avatar.stages.fakes.FakeAvatar` that just
muxes the still image and the audio is used instead.
"""

import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from ai_avatar.config import Config
from ai_avatar.errors import AiAvatarError, AvatarError
from ai_avatar.redact import scrub

log = logging.getLogger(__name__)

DOWNLOAD_HINT = "Download the weights with: cd models/sad_talker && bash scripts/download_models.sh"
GFPGAN_WEIGHTS = Path("gfpgan") / "weights" / "GFPGANv1.4.pth"


@contextmanager
def _sadtalker_context(cfg: Config, chdir: bool = False):
    """Make the SadTalker submodule importable and independent of the CWD.

    * The project root goes on ``sys.path`` so ``models.sad_talker.inference`` imports.
    * The submodule dir goes first so SadTalker's own ``src`` package wins over this
      repo's ``src/`` directory (which would otherwise import as an empty namespace package).
    * ``inference.py`` builds its config path from ``sys.argv[0]``, so we point ``argv[0]``
      at the project root for the call instead of editing the submodule.
    * With ``chdir`` the CWD becomes the submodule dir, because the GFPGAN enhancer looks for its
      weights in ``./gfpgan/weights`` relative to the CWD.

    Everything is restored on exit, including when SadTalker raises.
    """
    entries = [str(cfg.sadtalker_dir), str(cfg.root)]  # inserted so sadtalker_dir ends up first
    saved_argv0, saved_cwd = sys.argv[0], os.getcwd()
    for entry in reversed(entries):
        sys.path.insert(0, entry)
    sys.argv[0] = str(cfg.root / "ai-avatar")
    if chdir:
        os.chdir(cfg.sadtalker_dir)
    try:
        yield
    finally:
        if chdir:
            os.chdir(saved_cwd)
        sys.argv[0] = saved_argv0
        for entry in entries:
            sys.path.remove(entry)


def missing_sadtalker_files(cfg: Config) -> list[Path]:
    """Files the configured SadTalker setup needs but that are not on disk (empty when ready)."""
    checkpoints = cfg.sadtalker_checkpoints
    mapping = "mapping_00109-model.pth.tar" if "full" in cfg.avatar.preprocess else "mapping_00229-model.pth.tar"
    needed = [checkpoints / f"SadTalker_V0.0.2_{cfg.avatar.size}.safetensors", checkpoints / mapping]
    if cfg.avatar.enhancer == "gfpgan":
        needed.append(cfg.sadtalker_dir / GFPGAN_WEIGHTS)
    return [path for path in needed if not path.is_file()]


def _check_inputs(audio_path: Path, image_path: Path, cfg: Config) -> None:
    if not image_path.is_file():
        raise AvatarError(f"Avatar source image not found: {image_path}. Set avatar.image or pass --avatar-image.")
    if not audio_path.is_file():
        raise AvatarError(f"Audio not found: {audio_path}. Run the tts stage first or pass --audio.")
    if cfg.offline:
        return
    # SadTalker reads its model configs from <root>/models/sad_talker/src/config (see _sadtalker_context).
    if not (cfg.sadtalker_dir / "inference.py").is_file() or not (cfg.root / "models/sad_talker/src/config").is_dir():
        raise AvatarError(
            f"SadTalker is not checked out at {cfg.root / 'models/sad_talker'}. Run: git submodule update --init"
        )
    if missing := missing_sadtalker_files(cfg):
        names = ", ".join(str(p.relative_to(cfg.sadtalker_dir)) for p in missing)
        raise AvatarError(f"SadTalker files missing in {cfg.sadtalker_dir}: {names}. {DOWNLOAD_HINT}")


def _run_sadtalker(cfg: Config, **options) -> None:
    """Call SadTalker's programmatic ``run`` (heavy imports; requires the `avatar` extra)."""
    with _sadtalker_context(cfg, chdir=cfg.avatar.enhancer == "gfpgan"):
        try:
            from models.sad_talker.inference import run
        except ImportError as exc:
            raise AvatarError(
                f"SadTalker needs the optional dependency {exc.name!r}, which is not installed. "
                "Install it with: pip install -e '.[avatar]'"
            ) from exc
        run(**options)


def generate_avatar(audio_path: Path, image_path: Path, result_dir: Path, cfg: Config) -> Path:
    """Render the talking-head video into ``result_dir`` and return its path.

    ``result_dir`` should be private to the run: the output is whichever ``.mp4`` is new or modified
    in it after SadTalker returns (``run`` itself returns nothing; it names the file by timestamp).
    """
    audio_path, image_path, result_dir = (p.resolve() for p in (audio_path, image_path, result_dir))
    _check_inputs(audio_path, image_path, cfg)
    result_dir.mkdir(parents=True, exist_ok=True)
    before = {p: p.stat().st_mtime_ns for p in result_dir.glob("*.mp4")}

    options = {
        "driven_audio": str(audio_path),
        "source_image": str(image_path),
        "result_dir": str(result_dir),
        "size": cfg.avatar.size,
        "enhancer": None if cfg.avatar.enhancer == "none" else cfg.avatar.enhancer,
        "pose_style": cfg.avatar.pose_style,
        "expression_scale": cfg.avatar.expression_scale,
        "still": cfg.avatar.still,
        "preprocess": cfg.avatar.preprocess,
    }
    if cfg.offline:
        from ai_avatar.stages.fakes import FakeAvatar

        render = FakeAvatar().run
    else:
        options["checkpoint_dir"] = str(cfg.sadtalker_checkpoints.resolve())

        def render(**opts):
            _run_sadtalker(cfg, **opts)

    log.info("Rendering avatar (size %s, enhancer %s)", options["size"], options["enhancer"])
    try:
        render(**options)
    except AiAvatarError:
        raise
    except Exception as exc:
        raise AvatarError(f"SadTalker failed: {scrub(exc)}") from exc

    new = sorted(
        (p for p in result_dir.glob("*.mp4") if before.get(p) != p.stat().st_mtime_ns),
        key=lambda p: p.stat().st_mtime_ns,
    )
    if not new:
        raise AvatarError(
            f"SadTalker finished but wrote no video to {result_dir}. It exits silently when it cannot find a "
            f"face in the source image; check that {image_path.name} shows a clear, front-facing face."
        )
    if len(new) > 1:
        log.warning("SadTalker wrote %d videos to %s; using the newest: %s", len(new), result_dir, new[-1].name)
    if new[-1].stat().st_size == 0:
        raise AvatarError(f"SadTalker wrote an empty video: {new[-1]}")
    return new[-1]
