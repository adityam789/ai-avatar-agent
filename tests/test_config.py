"""Config loading: defaults, file/env overrides, path resolution."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_avatar.config import load_config, project_root


def test_defaults_load():
    cfg = load_config(environ={})
    assert (cfg.video.width, cfg.video.height) == (1080, 1920)
    assert (cfg.root / "config" / "default.yaml").is_file()
    assert cfg.llm.models


def test_paths_resolve_against_root_not_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config(environ={})
    assert cfg.outputs_dir == project_root() / "outputs"
    assert cfg.sadtalker_checkpoints == project_root() / "models/sad_talker/checkpoints"
    assert cfg.resolve("/abs/x.png") == Path("/abs/x.png")


def test_file_and_env_overrides(tmp_path):
    override = tmp_path / "o.yaml"
    override.write_text("background:\n  enabled: false\navatar:\n  height_ratio: 0.4\n")
    cfg = load_config(override, environ={"AI_AVATAR__tts__device": "cpu", "AI_AVATAR__video__width": "720"})
    assert cfg.background.enabled is False
    assert cfg.avatar.height_ratio == 0.4
    assert cfg.tts.device == "cpu"
    assert cfg.video.width == 720
    assert cfg.avatar.image  # untouched default survives the merge


def test_unknown_key_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("video:\n  widht: 1\n")
    with pytest.raises(ValidationError):
        load_config(bad, environ={})


def test_root_env_var_and_root_not_overridable(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_AVATAR_ROOT", str(tmp_path))
    assert project_root() == tmp_path.resolve()
    monkeypatch.delenv("AI_AVATAR_ROOT")
    cfg = load_config(environ={"AI_AVATAR__root": "/evil"})
    assert cfg.root == project_root()
