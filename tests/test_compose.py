"""Unit tests for the compose stage: the pure command builder and error handling (no real ffmpeg)."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_avatar.config import load_config
from ai_avatar.errors import ComposeError
from ai_avatar.stages import compose as compose_mod
from ai_avatar.stages.compose import build_ffmpeg_cmd


def test_build_ffmpeg_cmd_snapshot():
    cmd = build_ffmpeg_cmd(
        Path("avatar.mp4"), Path("loop.mp4"), Path("final.mp4"),
        duration=12.3456, width=1080, height=1920, avatar_height=1056, preset="veryfast", crf=20,
    )  # fmt: skip
    assert cmd == [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", "avatar.mp4",
        "-stream_loop", "-1", "-i", "loop.mp4",
        "-filter_complex",
        (
            "[0:v]fps=25,scale=1080:1056:force_original_aspect_ratio=increase,crop=1080:1056[top];"
            "[1:v]fps=25,scale=1080:864:force_original_aspect_ratio=increase,crop=1080:864[bottom];"
            "[top][bottom]vstack=inputs=2[v]"
        ),
        "-map", "[v]", "-map", "0:a?",
        "-t", "12.346",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-movflags", "+faststart",
        "final.mp4",
    ]  # fmt: skip


def test_both_tiles_are_cropped_not_stretched():
    cmd = build_ffmpeg_cmd(
        Path("a"), Path("b"), Path("c"), duration=1, width=100, height=200, avatar_height=120, preset="p", crf=1
    )
    filter_graph = cmd[cmd.index("-filter_complex") + 1]
    assert filter_graph.count("force_original_aspect_ratio=increase") == 2
    assert "crop=100:120[top]" in filter_graph and "crop=100:80[bottom]" in filter_graph


@pytest.fixture
def stubbed(tmp_path, monkeypatch):
    """compose() with ffmpeg/ffprobe 'installed' and subprocess.run replaced by a recorder."""
    (tmp_path / "a.mp4").write_text("x")
    (tmp_path / "l.mp4").write_text("x")
    monkeypatch.setattr(compose_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    calls = []
    state = SimpleNamespace(duration="3.5", returncode=0, stderr="", calls=calls)

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, stdout=state.duration + "\n", stderr="")
        return subprocess.CompletedProcess(cmd, state.returncode, stdout="", stderr=state.stderr)

    monkeypatch.setattr(compose_mod.subprocess, "run", fake_run)
    state.args = (tmp_path / "a.mp4", tmp_path / "l.mp4", tmp_path / "out.mp4", load_config(environ={}))
    return state


def test_compose_uses_probed_duration_and_config(stubbed):
    cfg = stubbed.args[3]
    cfg.video.preset, cfg.video.crf, cfg.avatar.height_ratio = "slow", 18, 0.5555  # 1066.56 -> even 1066
    compose_mod.compose(*stubbed.args)
    cmd = stubbed.calls[-1]
    assert cmd[0] == "ffmpeg" and cmd[cmd.index("-t") + 1] == "3.500"
    assert cmd[cmd.index("-preset") + 1] == "slow" and cmd[cmd.index("-crf") + 1] == "18"
    assert "crop=1080:1066[top]" in cmd[cmd.index("-filter_complex") + 1]


def test_ffmpeg_failure_surfaces_the_stderr_tail(stubbed):
    stubbed.returncode = 1
    stubbed.stderr = "\n".join(f"noise line {i}" for i in range(50)) + "\nInvalid data found when processing input"
    with pytest.raises(ComposeError) as exc:
        compose_mod.compose(*stubbed.args)
    message = str(exc.value)
    assert "status 1" in message and "Invalid data found" in message
    assert "noise line 0" not in message  # only the tail


@pytest.mark.parametrize("missing", ["ffmpeg", "ffprobe"])
def test_missing_binary_gives_install_hint(stubbed, monkeypatch, missing):
    monkeypatch.setattr(compose_mod.shutil, "which", lambda name: None if name == missing else "/bin/x")
    with pytest.raises(ComposeError, match=f"{missing} not found on PATH.*brew install ffmpeg"):
        compose_mod.compose(*stubbed.args)


def test_missing_input_files_and_bad_duration_are_reported(stubbed):
    avatar, loop, out, cfg = stubbed.args
    with pytest.raises(ComposeError, match="background loop does not exist"):
        compose_mod.compose(avatar, loop.with_name("nope.mp4"), out, cfg)
    with pytest.raises(ComposeError, match="avatar video does not exist"):
        compose_mod.compose(avatar.with_name("nope.mp4"), loop, out, cfg)
    stubbed.duration = "N/A"
    with pytest.raises(ComposeError, match="Could not read the duration"):
        compose_mod.compose(avatar, loop, out, cfg)
    stubbed.duration = "0.0"
    with pytest.raises(ComposeError, match="no duration"):
        compose_mod.compose(avatar, loop, out, cfg)


def test_ffmpeg_stderr_tail_is_scrubbed(stubbed, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaSyFAKEKEY123456")
    stubbed.returncode = 1
    stubbed.stderr = "Error opening https://x.test/v.mp4?key=AIzaSyFAKEKEY123456"
    with pytest.raises(ComposeError) as exc:
        compose_mod.compose(*stubbed.args)
    assert "AIzaSyFAKEKEY123456" not in str(exc.value) and "Error opening" in str(exc.value)


def test_ffprobe_failure_includes_its_stderr_tail(tmp_path, monkeypatch):
    def failing_probe(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="a.mp4: Invalid data found when processing input")

    monkeypatch.setattr(compose_mod.subprocess, "run", failing_probe)
    with pytest.raises(ComposeError, match="ffprobe.*\n.*Invalid data found when processing input"):
        compose_mod.probe_duration(tmp_path / "a.mp4")


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "-2.0", "0"])
def test_non_finite_or_non_positive_durations_are_errors(stubbed, bad):
    stubbed.duration = bad
    with pytest.raises(ComposeError, match="no duration"):
        compose_mod.compose(*stubbed.args)
    assert all(call[0] == "ffprobe" for call in stubbed.calls)  # ffmpeg never ran
