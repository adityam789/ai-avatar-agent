"""CLI smoke tests: argument handling, exit codes, doctor, dry-run. No network or heavy deps."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ai_avatar import cli
from ai_avatar.checks import Check
from ai_avatar.errors import TTSError


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """Keep runs out of the real outputs/ dir and make .env loading a no-op."""
    monkeypatch.setenv("AI_AVATAR__paths__outputs_dir", str(tmp_path / "out"))
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for command in ("run", "research", "script", "doctor"):
        assert command in out


def test_python_dash_m_help_works():
    result = subprocess.run([sys.executable, "-m", "ai_avatar", "--help"], capture_output=True, text=True)
    assert result.returncode == 0 and "doctor" in result.stdout


def test_usage_errors_exit_two():
    with pytest.raises(SystemExit) as exc:
        cli.main(["run"])  # missing topic
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "x", "--from-stage", "nonsense"])
    assert exc.value.code == 2


def test_doctor_ok_when_core_tools_present(capsys, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(cli, "check_runtime", lambda: [Check("python", True, "3.10.0")])
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-or-secret-value-123")
    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert code == 0
    assert "[ok  ] ffmpeg" in out
    assert "env OPEN_ROUTER_API_KEY: set" in out
    assert "sk-or-secret-value-123" not in out  # names only, never values


def test_doctor_fails_without_ffmpeg(capsys, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert code == 1
    assert "[FAIL] ffmpeg" in out and "block everything" in out


def test_doctor_reports_missing_optional_deps_without_failing(capsys, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("importlib.util.find_spec", lambda name, *a: None)
    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert code == 0
    assert "[warn] torch: not installed" in out
    assert "[warn] TTS package: not installed" in out


@pytest.fixture
def ready_machine(tmp_path, monkeypatch):
    """Everything a real run needs is 'installed': tools, files, checkpoints, torch/TTS, key."""
    (tmp_path / "sad" / "checkpoints").mkdir(parents=True)
    image, loop = tmp_path / "me.png", tmp_path / "loop.mp4"
    image.write_text("x")
    loop.write_text("x")
    monkeypatch.setenv("AI_AVATAR__paths__sadtalker_dir", str(tmp_path / "sad"))
    monkeypatch.setenv("AI_AVATAR__avatar__image", str(image))
    monkeypatch.setenv("AI_AVATAR__background__loop", str(loop))
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-or-secret-value-123")
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("importlib.util.find_spec", lambda name, *a: object())
    monkeypatch.setattr(
        cli, "check_runtime", lambda: [Check("torch", True, "2.1.2 (cpu only)", False), Check("TTS package", True, "installed", False)]
    )


def test_dry_run_ready(ready_machine, capsys, monkeypatch):
    monkeypatch.setattr(cli.pipeline, "run", lambda *a, **k: pytest.fail("dry run must not run stages"))
    code = cli.main(["run", "OpenAI", "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0 and "Ready." in out
    assert "-openai/" in out and "research: -> research.json" in out
    assert "sk-or-secret-value-123" not in out


def test_dry_run_not_ready_without_torch_or_tts(ready_machine, capsys, monkeypatch):
    monkeypatch.setattr(cli, "check_runtime", lambda: [Check("torch", False, "not installed", False), Check("TTS package", False, "missing", False)])
    assert cli.main(["run", "x", "--dry-run"]) == 1
    assert "Not ready: required checks failed: torch, TTS package" in capsys.readouterr().out
    assert cli.main(["run", "x", "--dry-run", "--offline"]) == 0  # offline needs neither


def test_dry_run_needs_no_api_key_when_inputs_are_supplied(ready_machine, capsys, monkeypatch, tmp_path):
    monkeypatch.delenv("OPEN_ROUTER_API_KEY")
    script = tmp_path / "s.txt"
    script.write_text("hi")
    assert cli.main(["run", "x", "--dry-run"]) == 1
    capsys.readouterr()
    assert cli.main(["run", "x", "--dry-run", "--script-file", str(script), "--from-stage", "tts"]) == 0
    out = capsys.readouterr().out
    assert "only stage" not in out and "from stage: tts" in out and "script override" in out
    assert cli.main(["run", "x", "--dry-run", "--script-file", str(tmp_path / "nope.txt"), "--from-stage", "tts"]) == 1
    out = capsys.readouterr().out
    assert "[FAIL] options: Override file not found" in out


def test_dry_run_exit_one_when_required_check_fails(capsys, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert cli.main(["run", "x", "--dry-run"]) == 1
    assert "Not ready" in capsys.readouterr().out


def test_run_passes_options_through(monkeypatch, tmp_path, capsys):
    seen = {}

    def fake_run(topic, cfg, **kwargs):
        seen.update(topic=topic, cfg=cfg, **kwargs)
        return tmp_path / "final.mp4"

    monkeypatch.setattr(cli.pipeline, "run", fake_run)
    code = cli.main([
        "run", "black holes", "--no-background", "--device", "cpu", "--offline", "--resume", str(tmp_path),
        "--from-stage", "tts", "--avatar-image", "me.png", "--loop", "l.mp4", "--seed", "7",
    ])
    assert code == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "final.mp4")
    cfg = seen["cfg"]
    assert seen["topic"] == "black holes" and seen["from_stage"] == "tts" and seen["resume"] == tmp_path
    assert cfg.background.enabled is False and cfg.tts.device == "cpu" and cfg.offline is True
    assert cfg.avatar.image == Path("me.png").resolve() and cfg.background.loop == Path("l.mp4").resolve()


def test_expected_errors_print_message_without_traceback(monkeypatch, capsys):
    def boom(*a, **k):
        raise TTSError("tts stage needs the optional dependency 'TTS'. Install it with: pip install -e '.[tts]'")

    monkeypatch.setattr(cli.pipeline, "run", boom)
    code = cli.main(["run", "x"])
    err = capsys.readouterr().err
    assert code == 1
    assert err.startswith("error: tts stage needs")
    assert "Traceback" not in err


def test_verbose_shows_traceback_and_scrubs_secrets(monkeypatch, capsys):
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaSyFAKEKEY123456")

    def boom(*a, **k):
        raise TTSError("failed calling /v1?key=AIzaSyFAKEKEY123456")

    monkeypatch.setattr(cli.pipeline, "run", boom)
    code = cli.main(["run", "x", "-v"])
    err = capsys.readouterr().err
    assert code == 1 and "Traceback" in err
    assert "AIzaSyFAKEKEY123456" not in err


def test_unexpected_error_exit_70_and_interrupt_130(monkeypatch, capsys):
    monkeypatch.setattr(cli.pipeline, "run", lambda *a, **k: 1 / 0)
    assert cli.main(["run", "x"]) == 70
    err = capsys.readouterr().err
    assert "ZeroDivisionError" in err and "Traceback" not in err and "-v" in err

    def interrupt(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.pipeline, "run", interrupt)
    assert cli.main(["run", "x"]) == 130


def test_bad_config_file_is_a_clean_error(tmp_path, capsys):
    assert cli.main(["run", "x", "--config", str(tmp_path / "missing.yaml")]) == 1
    assert "Config file not found" in capsys.readouterr().err
    bad = tmp_path / "bad.yaml"
    bad.write_text("video:\n  widht: 1\n")
    assert cli.main(["run", "x", "--config", str(bad)]) == 1
    assert "Invalid configuration" in capsys.readouterr().err


def test_research_and_script_subcommands_use_partial_runs(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_run(topic, cfg, **kwargs):
        calls.append(kwargs.get("only_stage"))
        if kwargs["only_stage"] == "research":
            path = tmp_path / "research.json"
            path.write_text(json.dumps({"topic": topic, "facts": ["a fact"]}))
        else:
            path = tmp_path / "script.txt"
            path.write_text("the script")
        return path

    monkeypatch.setattr(cli.pipeline, "run", fake_run)
    assert cli.main(["research", "x"]) == 0
    assert "a fact" in capsys.readouterr().out
    assert cli.main(["script", "x"]) == 0
    assert capsys.readouterr().out.strip() == "the script"
    assert calls == ["research", "research", "script"]


def test_stage_flags_need_earlier_results(capsys):
    assert cli.main(["run", "x", "--from-stage", "tts"]) == 1
    assert "needs earlier results" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "x", "--from-stage", "tts", "--only-stage", "avatar"])
    assert exc.value.code == 2


def test_seed_is_applied_and_validated(monkeypatch, tmp_path):
    seeded = []
    monkeypatch.setattr(cli, "_seed_everything", seeded.append)
    monkeypatch.setattr(cli.pipeline, "run", lambda *a, **k: tmp_path / "final.mp4")
    assert cli.main(["run", "x", "--seed", "42"]) == 0
    assert seeded == [42]
    for bad in ("-1", str(2**32), "abc"):
        with pytest.raises(SystemExit) as exc:
            cli.main(["run", "x", "--seed", bad])
        assert exc.value.code == 2


def test_audio_script_only_stage_passthrough(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(cli.pipeline, "run", lambda topic, cfg, **kw: seen.update(kw) or tmp_path / "f.mp4")
    wav, txt = tmp_path / "a.wav", tmp_path / "s.txt"
    assert cli.main(["run", "x", "--audio", str(wav), "--script-file", str(txt), "--only-stage", "avatar", "--resume", str(tmp_path)]) == 0
    assert seen["audio"] == wav and seen["script_file"] == txt and seen["only_stage"] == "avatar" and seen["resume"] == tmp_path


def test_cli_paths_are_relative_to_cwd_not_project_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    seen = {}
    monkeypatch.setattr(cli.pipeline, "run", lambda topic, cfg, **kw: seen.update(kw) or tmp_path / "f.mp4")
    cli.main(["run", "x", "--audio", "a.wav", "--resume", "somedir"])
    assert seen["audio"] == (tmp_path / "a.wav").resolve() and seen["resume"] == (tmp_path / "somedir").resolve()


def test_doctor_only_marks_core_problems_as_fail(ready_machine, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("AI_AVATAR__paths__sadtalker_dir", str(tmp_path / "nonexistent"))
    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert code == 0
    assert "[warn] SadTalker checkpoints" in out and "[FAIL]" not in out
    assert "Not ready for a real (non-offline) run yet: SadTalker checkpoints" in out


def test_doctor_survives_a_broken_torch(monkeypatch, capsys):
    import types

    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("importlib.util.find_spec", lambda name, *a: object() if name == "torch" else None)

    class Boom(types.ModuleType):
        def __getattr__(self, name):
            raise OSError("libcudart.so not found")

    monkeypatch.setitem(sys.modules, "torch", Boom("torch"))
    assert cli.main(["doctor"]) == 0
    assert "installed but fails to import: OSError" in capsys.readouterr().out


def test_research_and_script_with_real_pipeline_and_stubbed_functions(monkeypatch, capsys):
    from ai_avatar.research.schemas import ResearchBundle

    monkeypatch.setattr(
        "ai_avatar.research.run_research", lambda topic, cfg: ResearchBundle(topic, ["f1", "f2"], "fresh", ["rss"])
    )
    monkeypatch.setattr("ai_avatar.stages.script.generate_script", lambda topic, facts, cfg: f"{topic}: " + " ".join(facts))
    assert cli.main(["research", "owls"]) == 0
    assert json.loads(capsys.readouterr().out)["facts"] == ["f1", "f2"]
    assert cli.main(["script", "owls"]) == 0
    assert capsys.readouterr().out.strip() == "owls: f1 f2"


def test_dry_run_requirements_follow_the_stages_that_will_run(ready_machine, capsys, monkeypatch, tmp_path):
    no_heavy = [Check("torch", False, "not installed", False), Check("TTS package", False, "missing", False)]
    monkeypatch.setattr(cli, "check_runtime", lambda: no_heavy)
    monkeypatch.delenv("OPEN_ROUTER_API_KEY")
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    (run_dir / "avatar.mp4").write_text("v")
    wav = tmp_path / "a.wav"
    wav.write_text("w")

    # compose only needs ffmpeg: no key, torch or TTS
    assert cli.main(["run", "x", "--dry-run", "--resume", str(run_dir), "--only-stage", "compose"]) == 0
    out = capsys.readouterr().out
    assert "compose: -> final.mp4" in out and "research: skipped" in out

    # an audio override skips synthesis: torch needed (avatar), TTS package and key are not
    assert cli.main(["run", "x", "--dry-run", "--audio", str(wav), "--from-stage", "avatar"]) == 1
    assert "Not ready: required checks failed: torch" in capsys.readouterr().out.replace("torch, ", "torch")

    # a plain resume of a run that already has avatar.mp4 only has compose left to do
    assert cli.main(["run", "x", "--dry-run", "--resume", str(run_dir)]) == 0
    assert "tts: skipped" in capsys.readouterr().out

    # a fresh run needs everything
    assert cli.main(["run", "x", "--dry-run"]) == 1
    assert "env OPEN_ROUTER_API_KEY" in capsys.readouterr().out.split("Not ready")[1]


def test_dry_run_rejects_what_pipeline_run_rejects(ready_machine, capsys, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_text("w")
    assert cli.main(["run", "x", "--dry-run", "--resume", str(tmp_path / "nonexistent")]) == 1
    assert "[FAIL] options: --resume directory does not exist" in capsys.readouterr().out
    assert cli.main(["run", "x", "--dry-run", "--audio", str(wav), "--from-stage", "script"]) == 1
    assert "[FAIL] options" in capsys.readouterr().out


def test_dry_run_rejects_resume_dirs_missing_inputs_or_for_another_topic(ready_machine, capsys, tmp_path):
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    (run_dir / "research.json").write_text("{}")
    assert cli.main(["run", "x", "--dry-run", "--resume", str(run_dir), "--from-stage", "tts"]) == 1
    assert "needs script.txt" in capsys.readouterr().out
    (run_dir / "run.json").write_text(json.dumps({"topic": "other"}))
    assert cli.main(["run", "x", "--dry-run", "--resume", str(run_dir)]) == 1
    assert "was created for topic 'other'" in capsys.readouterr().out


def test_dry_run_requires_checkpoints_image_and_loop_only_for_the_stages_that_read_them(
    ready_machine, capsys, tmp_path, monkeypatch
):
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    (run_dir / "avatar.mp4").write_text("v")
    (tmp_path / "sad" / "checkpoints").rmdir()  # weights not downloaded
    (tmp_path / "me.png").unlink()  # avatar image missing (e.g. fresh clone without the submodule)
    compose_only = ["run", "x", "--dry-run", "--resume", str(run_dir), "--only-stage", "compose"]
    assert cli.main(compose_only) == 0  # compose reads neither
    assert "Ready." in capsys.readouterr().out
    assert cli.main(["run", "x", "--dry-run", "--offline", "--resume", str(run_dir), "--only-stage", "compose"]) == 0
    capsys.readouterr()

    wav = tmp_path / "a.wav"
    wav.write_text("w")
    avatar_on = ["run", "x", "--dry-run", "--audio", str(wav), "--from-stage", "avatar"]
    assert cli.main(avatar_on) == 1
    out = capsys.readouterr().out
    assert "SadTalker checkpoints" in out.split("Not ready")[1] and "avatar image" in out.split("Not ready")[1]

    (tmp_path / "loop.mp4").unlink()  # loop is needed by compose, which a from-avatar run also plans
    (tmp_path / "me.png").write_text("x")
    (tmp_path / "sad" / "checkpoints").mkdir()
    assert cli.main(avatar_on) == 1
    assert "background loop" in capsys.readouterr().out.split("Not ready")[1]
    assert cli.main([*avatar_on, "--offline"]) == 1  # offline fakes still need the loop file
    capsys.readouterr()
    (tmp_path / "loop.mp4").write_text("x")
    assert cli.main(avatar_on) == 0
