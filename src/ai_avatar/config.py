"""Typed configuration loaded from YAML, with env-var overrides.

Load order (later wins): ``config/default.yaml`` -> ``--config FILE`` ->
``AI_AVATAR__<section>__<key>=<yaml value>`` environment variables.
Relative paths in the config are resolved against the project root, never the CWD.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

ENV_PREFIX = "AI_AVATAR__"


def project_root() -> Path:
    """Directory containing ``config/`` and ``models/``.

    ``AI_AVATAR_ROOT`` wins; otherwise walk up from this file to the first directory
    containing ``config/default.yaml`` (source/editable checkouts), else the CWD. A
    non-editable install does not ship ``config/`` and needs ``AI_AVATAR_ROOT``.
    """
    if env := os.getenv("AI_AVATAR_ROOT"):
        return Path(env).resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / "config" / "default.yaml").is_file():
            return parent
    return Path.cwd()


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoConfig(_Section):
    width: int = 1080
    height: int = 1920


class AvatarConfig(_Section):
    image: Path
    height_ratio: float = 0.55


class BackgroundConfig(_Section):
    enabled: bool = True
    loop: Path


class TTSConfig(_Section):
    # ``device`` auto/mps handling arrives in Task 08; today only "cuda" enables the GPU.
    voice: str = "Ana Florence"
    language: str = "en"
    device: Literal["auto", "cpu", "cuda", "mps"] = "auto"


class LLMConfig(_Section):
    # Consumed by LLMClient in Task 07 (currently the client hard-codes its own URL/model).
    base_url: str = "https://openrouter.ai/api/v1/chat/completions"
    models: list[str]


class PathsConfig(_Section):
    # Note: the SadTalker import is still hard-wired to ``models.sad_talker`` (the submodule
    # path), so ``sadtalker_dir`` is only honoured for locating checkpoints and its ``src``.
    outputs_dir: Path = Path("outputs")
    sadtalker_dir: Path = Path("models/sad_talker")


class Config(_Section):
    root: Path
    video: VideoConfig = VideoConfig()
    avatar: AvatarConfig
    background: BackgroundConfig
    tts: TTSConfig = TTSConfig()
    llm: LLMConfig
    paths: PathsConfig = PathsConfig()

    def resolve(self, path: Path | str) -> Path:
        """Absolute version of ``path``; relative paths are taken from the project root."""
        p = Path(path).expanduser()
        return p if p.is_absolute() else self.root / p

    @property
    def outputs_dir(self) -> Path:
        return self.resolve(self.paths.outputs_dir)

    @property
    def sadtalker_dir(self) -> Path:
        return self.resolve(self.paths.sadtalker_dir)

    @property
    def sadtalker_checkpoints(self) -> Path:
        return self.sadtalker_dir / "checkpoints"


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def _env_overrides(environ: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, raw in environ.items():
        if not name.startswith(ENV_PREFIX):
            continue
        *sections, key = name[len(ENV_PREFIX) :].split("__")
        node = out
        for section in sections:
            node = node.setdefault(section, {})
        node[key] = yaml.safe_load(raw)
    return out


def load_config(path: Path | str | None = None, environ: dict[str, str] | None = None) -> Config:
    """Build a :class:`Config` from defaults, an optional override file and env vars."""
    root = project_root()
    data = yaml.safe_load((root / "config" / "default.yaml").read_text()) or {}
    if path is not None:
        _merge(data, yaml.safe_load(Path(path).read_text()) or {})
    _merge(data, _env_overrides(dict(os.environ if environ is None else environ)))
    return Config(**{**data, "root": root})  # root is never overridable from files/env
