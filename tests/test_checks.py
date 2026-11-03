"""check_environment: what a real run requires versus what an offline (fakes only) run requires."""

import pytest

from ai_avatar.checks import check_environment
from ai_avatar.config import load_config


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Nothing but ffmpeg/ffprobe, the avatar image and the loop exist; no checkpoints, no API key."""
    monkeypatch.delenv("OPEN_ROUTER_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    cfg = load_config(environ={})
    cfg.root = tmp_path
    cfg.avatar.image = tmp_path / "me.png"
    cfg.background.loop = tmp_path / "loop.mp4"
    cfg.avatar.image.write_text("x")
    cfg.background.loop.write_text("x")
    return cfg


def required_failures(cfg):
    return {c.name for c in check_environment(cfg) if c.required and not c.ok}


def test_real_run_requires_checkpoints_and_api_key(cfg):
    assert required_failures(cfg) == {"SadTalker checkpoints", "env OPEN_ROUTER_API_KEY"}


def test_offline_run_does_not_require_checkpoints_or_api_key(cfg):
    cfg.offline = True
    assert required_failures(cfg) == set()
    # still reported, just not required
    names = {c.name: c for c in check_environment(cfg)}
    assert not names["SadTalker checkpoints"].ok and not names["env OPEN_ROUTER_API_KEY"].ok


def test_offline_run_still_requires_ffmpeg_image_and_loop(cfg, monkeypatch):
    cfg.offline = True
    monkeypatch.setattr("shutil.which", lambda name: None)
    cfg.avatar.image.unlink()
    cfg.background.loop.unlink()
    assert required_failures(cfg) == {"ffmpeg", "ffprobe", "avatar image", "background loop"}
