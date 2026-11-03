"""Staged, resumable pipeline: topic -> research -> script -> speech -> avatar -> final video.

Every stage reads files in the run directory and writes exactly one artifact, so a run can be
inspected, resumed (``resume=``), partly re-run (``from_stage=`` / ``only_stage=``) or fed
pre-made inputs (``audio=`` / ``script_file=``) without touching the network or a GPU.

Run layout::

    outputs/<YYYYmmdd-HHMMSS>-<topic-slug>/
        research.json  script.txt  audio.wav  avatar.mp4  final.mp4  run.json
        sadtalker/      (SadTalker's own scratch/output dir; avatar.mp4 is copied from it)
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import platform
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ai_avatar import __version__
from ai_avatar.checks import Check, check_environment
from ai_avatar.config import Config, load_config
from ai_avatar.redact import scrub
from ai_avatar.errors import (
    AiAvatarError,
    AvatarError,
    ComposeError,
    LLMError,
    PipelineError,
    ResearchError,
    TTSError,
)

log = logging.getLogger(__name__)


@dataclass
class RunContext:
    """Everything a stage needs: the topic, config and the run directory with its artifact paths."""

    topic: str
    cfg: Config
    run_dir: Path
    run_id: str

    def path(self, artifact: str) -> Path:
        return self.run_dir / artifact


@dataclass(frozen=True)
class Stage:
    """One pipeline step: ``fn(ctx)`` must write ``artifact`` into the run dir."""

    name: str
    artifact: str
    fn: Callable[[RunContext], None]
    error: type[AiAvatarError]
    requires: str | None = None  # artifact this stage reads
    extra: str | None = None  # pip extra that provides this stage's heavy dependencies


# --- real stage adapters (heavy imports happen inside, so importing this module stays light) ---


def _research(ctx: RunContext) -> None:
    from dataclasses import asdict

    from ai_avatar.research import run_research

    bundle = run_research(ctx.topic, ctx.cfg)
    ctx.path("research.json").write_text(json.dumps(asdict(bundle), indent=2))


def _script(ctx: RunContext) -> None:
    from ai_avatar.stages.script import generate_script

    facts = json.loads(ctx.path("research.json").read_text())["facts"]
    ctx.path("script.txt").write_text(generate_script(ctx.topic, facts, ctx.cfg))


def _tts(ctx: RunContext) -> None:
    from ai_avatar.stages.tts import generate_audio

    generate_audio(ctx.path("script.txt").read_text(), ctx.path("audio.wav"), ctx.cfg)


def _avatar(ctx: RunContext) -> None:
    from ai_avatar.stages.avatar import generate_avatar

    video = generate_avatar(
        ctx.path("audio.wav"), ctx.cfg.resolve(ctx.cfg.avatar.image), ctx.path("sadtalker"), ctx.cfg
    )
    shutil.copyfile(video, ctx.path("avatar.mp4"))


def _compose(ctx: RunContext) -> None:
    cfg = ctx.cfg
    if not cfg.background.enabled:
        shutil.copyfile(ctx.path("avatar.mp4"), ctx.path("final.mp4"))
        return
    from ai_avatar.stages.compose import compose

    compose(ctx.path("avatar.mp4"), cfg.resolve(cfg.background.loop), ctx.path("final.mp4"), cfg)


DEFAULT_STAGES: tuple[Stage, ...] = (
    Stage("research", "research.json", _research, ResearchError),
    Stage("script", "script.txt", _script, LLMError, requires="research.json"),
    Stage("tts", "audio.wav", _tts, TTSError, requires="script.txt", extra="tts"),
    Stage("avatar", "avatar.mp4", _avatar, AvatarError, requires="audio.wav", extra="avatar"),
    Stage("compose", "final.mp4", _compose, ComposeError, requires="avatar.mp4"),
)


# --- helpers ---


def slugify(text: str, max_len: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:max_len].strip("-") or "topic"


def config_hash(cfg: Config) -> str:
    """Stable short hash of the effective config (no secrets live in it; ``root`` is excluded)."""
    payload = cfg.model_dump(mode="json", exclude={"root"})
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def _stage_index(stages: tuple[Stage, ...], name: str) -> int:
    for i, stage in enumerate(stages):
        if stage.name == name:
            return i
    raise PipelineError(f"Unknown stage {name!r}. Choose from: {', '.join(s.name for s in stages)}")


def _write_run_json(ctx: RunContext, record: dict) -> None:
    ctx.path("run.json").write_text(json.dumps(record, indent=2))


def _read_run_json(run_dir: Path) -> dict:
    path = run_dir / "run.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise PipelineError(f"{path} is corrupt ({exc}); delete it to start the record afresh.") from exc


def _installed_versions() -> dict[str, str]:
    versions = {}
    for package in ("coqui-tts", "TTS", "torch"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    return versions


def _explain(stage: Stage, exc: BaseException) -> str:
    """Actionable message for an unexpected exception raised inside ``stage``."""
    if isinstance(exc, ImportError) and stage.extra:
        return (
            f"{stage.name} stage needs the optional dependency {exc.name or 'it imports'!r}, which is not installed. "
            f"Install it with: pip install -e '.[{stage.extra}]'"
        )
    if isinstance(exc, subprocess.CalledProcessError):
        return f"{stage.name} stage: `{Path(str(exc.cmd[0])).name}` exited with status {exc.returncode}"
    return f"{stage.name} stage failed: {scrub(exc)}"


def _make_run_dir(base: Path, stamp: str, slug: str) -> Path:
    for n in range(1, 100):
        run_dir = base / f"{stamp}-{slug}{'' if n == 1 else f'-{n}'}"
        try:
            run_dir.mkdir(parents=True)
            return run_dir
        except FileExistsError:
            continue
    raise PipelineError(f"Could not create a unique run directory under {base}")


# --- public API ---


def run(
    topic: str,
    cfg: Config | None = None,
    *,
    resume: Path | None = None,
    from_stage: str | None = None,
    only_stage: str | None = None,
    audio: Path | None = None,
    script_file: Path | None = None,
    stages: tuple[Stage, ...] = DEFAULT_STAGES,
) -> Path:
    """Run the pipeline for ``topic`` and return the path of the last artifact produced
    (``final.mp4`` for a full run).

    Stage selection: a stage is skipped when its artifact -- or any later stage's artifact --
    already exists in the run dir. ``from_stage`` forces that stage and everything after it to
    re-run; ``only_stage`` re-runs just that one and leaves later artifacts untouched (they become
    stale -- a warning says so -- until you re-run with ``from_stage``). ``audio`` / ``script_file``
    are copied into the run dir as ``audio.wav`` / ``script.txt``, which makes the earlier stages
    unnecessary and discards later artifacts. An override the selected stage range would overwrite
    is rejected. Re-running a stage deletes its old artifact and all later ones first.
    """
    cfg = cfg or load_config()
    if from_stage and only_stage:
        raise PipelineError("Use either from_stage or only_stage, not both.")
    first = _stage_index(stages, from_stage) if from_stage else None
    only = _stage_index(stages, only_stage) if only_stage else None
    overrides = [(script_file, "script.txt"), (audio, "audio.wav")]
    for source, artifact in overrides:
        if source is None:
            continue
        if not Path(source).is_file():
            raise PipelineError(f"Override file not found: {source}")
    selected = first if first is not None else only
    override_indexes = [next(i for i, st in enumerate(stages) if st.artifact == a) for src, a in overrides if src is not None]
    if selected is not None and override_indexes and selected != max(override_indexes) + 1:
        want = stages[max(override_indexes) + 1].name if max(override_indexes) + 1 < len(stages) else "(none)"
        raise PipelineError(
            f"--audio/--script-file feed the {want!r} stage, so they can only be combined with "
            f"from_stage/only_stage={want!r}, not {stages[selected].name!r}."
        )

    if resume:
        run_dir = Path(resume).resolve()
        if not run_dir.is_dir():
            raise PipelineError(f"--resume directory does not exist: {run_dir}")
        previous = _read_run_json(run_dir)
        if previous.get("topic") not in (None, topic):
            raise PipelineError(
                f"{run_dir.name} was created for topic {previous['topic']!r}, not {topic!r}. "
                "Resume with the original topic or start a new run."
            )
    else:
        previous = {}
        run_dir = _make_run_dir(cfg.outputs_dir, datetime.now().strftime("%Y%m%d-%H%M%S"), slugify(topic))
    ctx = RunContext(topic=topic, cfg=cfg, run_dir=run_dir, run_id=run_dir.name)
    stage_records = previous.get("stages", {})

    def invalidate_after(index: int) -> None:
        """Drop artifacts of stages after ``index``: they were derived from an input that changed."""
        for later in stages[index + 1 :]:
            stage_records.pop(later.name, None)
            if ctx.path(later.artifact).exists():
                log.info("Discarding stale %s", later.artifact)
                ctx.path(later.artifact).unlink()

    for source, artifact in overrides:
        if source is None:
            continue
        target = ctx.path(artifact)
        if target.exists() and Path(source).samefile(target):
            continue  # already in place
        shutil.copyfile(source, target)
        invalidate_after(next(i for i, s in enumerate(stages) if s.artifact == artifact))

    config_digest = config_hash(cfg)
    if previous.get("config_hash") not in (None, config_digest):
        log.warning("Config changed since this run was created; earlier artifacts may not match it.")
    record = {
        **previous,
        "topic": topic,
        "run_id": ctx.run_id,
        "started_at": previous.get("started_at") or datetime.now().isoformat(timespec="seconds"),
        "last_invoked_at": datetime.now().isoformat(timespec="seconds"),
        "ai_avatar_version": __version__,
        "python": platform.python_version(),
        "versions": _installed_versions(),
        "config_hash": config_digest,
        "models": {"llm": cfg.llm.models, "tts_voice": cfg.tts.voice, "tts_language": cfg.tts.language},
        "stages": stage_records,
    }
    record.pop("overrides", None)
    if audio is not None or script_file is not None:
        record["overrides"] = {"audio": audio is not None, "script_file": script_file is not None}
    _write_run_json(ctx, record)  # exists even if the first stage cannot start

    log.info("Run directory: %s", run_dir)
    last = run_dir
    for i, stage in enumerate(stages):
        artifact = ctx.path(stage.artifact)
        if only is not None:
            forced = i == only
            skip = not forced
        elif first is not None:
            forced = i >= first
            skip = i < first
        else:
            forced = False
            skip = any(ctx.path(s.artifact).is_file() for s in stages[i:])
        if skip:
            if only is None and artifact.is_file():
                last = artifact
            log.info("[%s] skipped", stage.name)
            continue
        if stage.requires and not ctx.path(stage.requires).is_file():
            raise PipelineError(
                f"Stage {stage.name!r} needs {stage.requires} in {run_dir}. "
                "Run the earlier stages first or pass the matching override (--audio / --script-file)."
            )
        log.info("[%s] running%s", stage.name, " (forced)" if forced else "")
        # Re-running a stage makes its old output and everything derived from it stale.
        artifact.unlink(missing_ok=True)
        stage_records.pop(stage.name, None)
        if only is None:
            invalidate_after(i)
        else:
            stale = [st.artifact for st in stages[i + 1 :] if ctx.path(st.artifact).exists()]
            if stale:
                log.warning("%s are now stale; re-run with --from-stage %s to refresh them.", ", ".join(stale), stages[i + 1].name)
        started = time.perf_counter()
        try:
            stage.fn(ctx)
            if not artifact.is_file():
                raise PipelineError(f"stage did not write {stage.artifact}")
        except BaseException as exc:  # incl. KeyboardInterrupt: never leave a partial artifact behind
            artifact.unlink(missing_ok=True)
            stage_records[stage.name] = {"status": "failed", "error": scrub(f"{type(exc).__name__}: {exc}")}
            _write_run_json(ctx, record)
            if isinstance(exc, AiAvatarError) or not isinstance(exc, Exception):
                raise
            raise stage.error(_explain(stage, exc)) from exc
        seconds = round(time.perf_counter() - started, 2)
        stage_records[stage.name] = {"status": "done", "seconds": seconds}
        log.info("[%s] done in %.1fs", stage.name, seconds)
        _write_run_json(ctx, record)
        last = artifact

    _write_run_json(ctx, record)
    return last


def dry_run(
    topic: str,
    cfg: Config | None = None,
    stages: tuple[Stage, ...] = DEFAULT_STAGES,
) -> tuple[list[str], list[Check]]:
    """Validate the setup without running anything.

    Returns ``(plan, checks)``: the stages/artifacts that would run, and environment checks
    (``Check.required`` ones must pass for a real run). Env var *names* only, never values.
    """
    cfg = cfg or load_config()
    plan = [f"{s.name}: -> {s.artifact}" for s in stages]
    plan.insert(0, f"run dir: {cfg.outputs_dir}/<timestamp>-{slugify(topic)}/")
    return plan, check_environment(cfg)
