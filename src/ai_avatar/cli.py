"""Command-line interface: ``ai-avatar run | research | script | doctor``.

Exit codes: 0 success, 1 expected failure (bad input, missing dependency, stage error),
2 usage error (argparse), 70 unexpected internal error, 130 interrupted.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import random
import sys
import traceback
from collections.abc import Collection, Sequence
from pathlib import Path

from ai_avatar import __version__, pipeline
from ai_avatar.checks import CORE_CHECKS, REAL_RUN_CHECKS, Check, check_environment, check_runtime
from ai_avatar.config import Config, load_config, project_root
from ai_avatar.errors import AiAvatarError, ConfigError, PipelineError
from ai_avatar.logging_setup import setup_logging
from ai_avatar.redact import scrub

log = logging.getLogger(__name__)
STAGE_NAMES = [s.name for s in pipeline.DEFAULT_STAGES]


def _seed(value: str) -> int:
    n = int(value)
    if not 0 <= n < 2**32:
        raise argparse.ArgumentTypeError("must be between 0 and 4294967295")
    return n


def _path(value: str) -> Path:
    """Paths given on the command line are relative to the CWD (config paths are relative to the project root)."""
    return Path(value).expanduser().resolve()


def _common_options() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=_path, metavar="FILE", help="YAML file overriding config/default.yaml")
    common.add_argument("-v", "--verbose", action="store_true", help="debug logging and full tracebacks")
    common.add_argument("-q", "--quiet", action="store_true", help="only warnings and errors")
    return common


def build_parser() -> argparse.ArgumentParser:
    common = _common_options()
    parser = argparse.ArgumentParser(
        prog="ai-avatar",
        description="Turn a topic into a vertical talking-head video: "
        "research -> LLM script -> TTS -> SadTalker avatar -> ffmpeg composite.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    run = sub.add_parser("run", parents=[common], help="generate a video for a topic")
    run.add_argument("topic")
    run.add_argument("--dry-run", action="store_true", help="validate setup and print the plan; run nothing")
    run.add_argument("--offline", action="store_true", help="fixtures + fake LLM/TTS/avatar: no network, keys or GPU")
    run.add_argument("--resume", type=_path, metavar="DIR", help="continue an existing run directory")
    which = run.add_mutually_exclusive_group()
    which.add_argument("--from-stage", choices=STAGE_NAMES, help="re-run this stage and everything after it")
    which.add_argument("--only-stage", choices=STAGE_NAMES, help="re-run just this stage")
    run.add_argument("--audio", type=_path, metavar="WAV", help="use this audio instead of synthesizing speech")
    run.add_argument(
        "--script-file", type=_path, metavar="TXT", help="use this script instead of researching/writing one"
    )
    run.add_argument("--avatar-image", type=_path, metavar="PNG", help="still image for the talking head")
    run.add_argument("--loop", type=_path, metavar="MP4", help="background loop video")
    run.add_argument("--no-background", action="store_true", help="output the avatar video without the background")
    run.add_argument("--device", choices=["auto", "cpu", "cuda", "mps"], help="TTS device (default: from config)")
    run.add_argument("--seed", type=_seed, help="seed Python/numpy/torch RNGs for repeatable runs")
    run.set_defaults(func=cmd_run)

    for name, func, help_text in (
        ("research", cmd_research, "run only the research stage and print the facts"),
        ("script", cmd_script, "run research + script and print the narration"),
    ):
        p = sub.add_parser(name, parents=[common], help=help_text)
        p.add_argument("topic")
        p.add_argument("--offline", action="store_true", help="use fixtures and the fake LLM")
        p.set_defaults(func=func)

    doctor = sub.add_parser("doctor", parents=[common], help="check this machine's setup (never prints secret values)")
    doctor.set_defaults(func=cmd_doctor)
    return parser


# --- helpers ---


def _load(args: argparse.Namespace) -> Config:
    from dotenv import load_dotenv

    load_dotenv(project_root() / ".env")  # fills os.environ only; values are never printed
    try:
        cfg = load_config(args.config)
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {exc.filename}") from exc
    except Exception as exc:  # pydantic.ValidationError, yaml.YAMLError, ...
        raise ConfigError(f"Invalid configuration: {exc}") from exc

    if getattr(args, "offline", False):
        cfg.offline = True
    if getattr(args, "avatar_image", None):
        cfg.avatar.image = args.avatar_image
    if getattr(args, "loop", None):
        cfg.background.loop = args.loop
    if getattr(args, "no_background", False):
        cfg.background.enabled = False
    if getattr(args, "device", None):
        cfg.tts.device = args.device
    return cfg


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch

        torch.manual_seed(seed)
    except ImportError:
        pass


def _print_checks(checks: Sequence[Check], failing: Collection[str] | None = None) -> None:
    """Print ``[ok]/[FAIL]/[warn]`` lines; ``failing`` limits which names may show FAIL (default: required ones)."""
    for c in checks:
        is_blocker = c.name in failing if failing is not None else c.required
        print(f"[{'ok  ' if c.ok else 'FAIL' if is_blocker else 'warn'}] {c.name}: {c.detail}")


def _check_stage_flags(args: argparse.Namespace) -> None:
    """Reject combinations pipeline.run would reject anyway, before creating any run directory."""
    stage = args.from_stage or args.only_stage
    has_input = args.resume or args.audio or args.script_file
    if stage and STAGE_NAMES.index(stage) > 0 and not has_input:
        raise PipelineError(
            f"--from-stage/--only-stage {stage} needs earlier results: pass --resume DIR, "
            "or --script-file / --audio to supply them."
        )


def _dry_run(args: argparse.Namespace, cfg: Config) -> int:
    options = dict(
        from_stage=args.from_stage, only_stage=args.only_stage, audio=args.audio, script_file=args.script_file
    )
    stages = pipeline.DEFAULT_STAGES
    extra: list[Check] = []
    try:
        will_run = pipeline.planned_stages(stages, topic=args.topic, run_dir=args.resume, **options)
    except PipelineError as exc:
        extra.append(Check("options", False, str(exc)))
        will_run = [s.name for s in stages]
    plan, checks = pipeline.dry_run(args.topic, cfg, will_run=will_run)

    # Only demand what the stages that will actually run need.
    needs = {
        "env OPEN_ROUTER_API_KEY": {"research", "script"},
        "TTS package": {"tts"},
        "torch": {"tts", "avatar"},
        "SadTalker checkpoints": {"avatar"},
    }
    # Inputs that offline mode still needs (the fakes replace models and services, not files), but only
    # for the stages that read them.
    needs_files = {"avatar image": {"avatar"}, "background loop": {"compose"}}
    adjusted = []
    for c in checks + check_runtime():
        if c.name in needs:
            c = dataclasses.replace(c, required=bool(needs[c.name] & set(will_run)) and not cfg.offline)
        elif c.name in needs_files:
            c = dataclasses.replace(c, required=bool(needs_files[c.name] & set(will_run)))
        adjusted.append(c)
    notes = [f"resume: {args.resume}"] if args.resume else []
    notes += [
        f"{flag}: {value}"
        for flag, value in (("from stage", args.from_stage), ("only stage", args.only_stage))
        if value
    ]
    notes += [
        f"{label} override: {path}" for label, path in (("script", args.script_file), ("audio", args.audio)) if path
    ]
    if not cfg.background.enabled:
        notes.append("background: disabled (avatar video is the final output)")
    adjusted += extra
    print("Plan:")
    for line in plan + notes:
        print(f"  {line}")
    print("\nChecks:")
    _print_checks(adjusted)
    failed = [c.name for c in adjusted if c.required and not c.ok]
    if failed:
        print(f"\nNot ready: required checks failed: {', '.join(failed)}")
        return 1
    print("\nReady.")
    return 0


# --- commands ---


def cmd_run(args: argparse.Namespace) -> int:
    cfg = _load(args)
    _check_stage_flags(args)
    if args.dry_run:
        return _dry_run(args, cfg)
    if args.seed is not None:
        _seed_everything(args.seed)
    final = pipeline.run(
        args.topic,
        cfg,
        resume=args.resume,
        from_stage=args.from_stage,
        only_stage=args.only_stage,
        audio=args.audio,
        script_file=args.script_file,
    )
    print(final)
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    out = pipeline.run(args.topic, _load(args), only_stage="research")
    bundle = json.loads(out.read_text())
    print(json.dumps(bundle, indent=2))
    log.info("Saved to %s", out)
    return 0


def cmd_script(args: argparse.Namespace) -> int:
    cfg = _load(args)
    research = pipeline.run(args.topic, cfg, only_stage="research")
    script = pipeline.run(args.topic, cfg, resume=research.parent, only_stage="script")
    print(script.read_text())
    log.info("Saved to %s", script)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = _load(args)
    checks = check_runtime() + check_environment(cfg)
    print(f"ai-avatar {__version__}  (project root: {cfg.root})")
    _print_checks(checks, failing=CORE_CHECKS)
    broken = [c.name for c in checks if c.name in CORE_CHECKS and not c.ok]
    if broken:
        print(f"\nProblems that block everything: {', '.join(broken)}")
        return 1
    missing = [c.name for c in checks if not c.ok and (c.required or c.name in REAL_RUN_CHECKS)]
    if missing:
        print(f"\nCore setup OK. Not ready for a real (non-offline) run yet: {', '.join(missing)}")
    else:
        print("\nAll checks passed.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    verbose = args.verbose
    setup_logging(1 if verbose else -1 if args.quiet else 0)
    try:
        return args.func(args)
    except AiAvatarError as err:
        print(f"error: {scrub(err)}", file=sys.stderr)
        if verbose:
            print(scrub(traceback.format_exc()), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except Exception as err:
        print(f"unexpected error: {type(err).__name__}: {scrub(err)}", file=sys.stderr)
        print(scrub(traceback.format_exc()) if verbose else "(re-run with -v for the traceback)", file=sys.stderr)
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
