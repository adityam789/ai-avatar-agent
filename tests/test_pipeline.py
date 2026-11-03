"""Pipeline orchestration with fake stages: no network, GPU or heavy imports."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from ai_avatar.checks import Check
from ai_avatar.config import load_config
from ai_avatar.errors import AvatarError, PipelineError, ResearchError, TTSError
from ai_avatar.research.schemas import ResearchBundle
from ai_avatar.pipeline import DEFAULT_STAGES, Stage, config_hash, dry_run, run, slugify


@pytest.fixture
def cfg(tmp_path):
    return load_config(environ={"AI_AVATAR__paths__outputs_dir": str(tmp_path / "out")})


@pytest.fixture
def calls():
    return []


@pytest.fixture
def fake_stages(calls):
    """Same shape as DEFAULT_STAGES; each stage records its call and writes a tiny artifact."""

    def make(name, artifact, error, requires=None, write=None):
        def fn(ctx):
            calls.append(name)
            ctx.path(artifact).write_text(write(ctx) if write else name)

        return Stage(name, artifact, fn, error, requires)

    base = {s.name: s for s in DEFAULT_STAGES}
    return (
        make("research", "research.json", base["research"].error, write=lambda c: json.dumps({"topic": c.topic, "facts": ["f"]})),
        make("script", "script.txt", base["script"].error, "research.json", write=lambda c: f"script about {c.topic}"),
        make("tts", "audio.wav", TTSError, "script.txt"),
        make("avatar", "avatar.mp4", AvatarError, "audio.wav"),
        make("compose", "final.mp4", base["compose"].error, "avatar.mp4"),
    )


def test_full_run_creates_run_dir_and_run_json(cfg, fake_stages, calls):
    final = run("OpenAI GPT-5!", cfg, stages=fake_stages)

    assert calls == ["research", "script", "tts", "avatar", "compose"]
    assert final.name == "final.mp4"
    run_dir = final.parent
    assert run_dir.parent == cfg.outputs_dir
    assert run_dir.name.endswith("-openai-gpt-5")
    assert {p.name for p in run_dir.iterdir()} == {
        "research.json", "script.txt", "audio.wav", "avatar.mp4", "final.mp4", "run.json",
    }
    record = json.loads((run_dir / "run.json").read_text())
    assert record["topic"] == "OpenAI GPT-5!"
    assert set(record["stages"]) == {"research", "script", "tts", "avatar", "compose"}
    assert all(s["status"] == "done" and "seconds" in s for s in record["stages"].values())
    assert record["config_hash"] == config_hash(cfg)
    assert record["models"]["llm"] == cfg.llm.models
    assert "ai_avatar_version" in record


def test_topic_flows_into_research_and_script(cfg, fake_stages):
    final = run("quantum computing", cfg, stages=fake_stages)
    assert json.loads((final.parent / "research.json").read_text())["topic"] == "quantum computing"
    assert "quantum computing" in (final.parent / "script.txt").read_text()


def test_run_json_has_only_expected_keys_and_no_env_values(cfg, fake_stages, monkeypatch):
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-super-secret-value")
    final = run("x", cfg, stages=fake_stages)
    text = (final.parent / "run.json").read_text()
    assert "sk-super-secret-value" not in text
    assert set(json.loads(text)) == {
        "topic", "run_id", "started_at", "last_invoked_at", "ai_avatar_version", "python",
        "versions", "config_hash", "models", "stages",
    }


def test_resume_skips_completed_stages(cfg, fake_stages, calls):
    final = run("topic", cfg, stages=fake_stages)
    run_dir = final.parent
    (run_dir / "final.mp4").unlink()
    (run_dir / "avatar.mp4").unlink()
    calls.clear()

    run("topic", cfg, resume=run_dir, stages=fake_stages)

    assert calls == ["avatar", "compose"]
    record = json.loads((run_dir / "run.json").read_text())
    assert record["stages"]["research"]["status"] == "done"  # timing from first invocation preserved


def test_resume_complete_run_does_nothing(cfg, fake_stages, calls):
    run_dir = run("t", cfg, stages=fake_stages).parent
    calls.clear()
    assert run("t", cfg, resume=run_dir, stages=fake_stages) == run_dir / "final.mp4"
    assert calls == []


def test_resume_after_failure_retries_only_failed_stage(cfg, fake_stages, calls):
    boom = Stage("avatar", "avatar.mp4", lambda ctx: (_ for _ in ()).throw(ValueError("gpu on fire")), AvatarError, "audio.wav")
    broken = fake_stages[:3] + (boom, fake_stages[4])
    with pytest.raises(AvatarError, match="avatar stage failed: gpu on fire"):
        run("t", cfg, stages=broken)
    run_dir = next(cfg.outputs_dir.iterdir())
    assert json.loads((run_dir / "run.json").read_text())["stages"]["avatar"]["status"] == "failed"
    calls.clear()

    run("t", cfg, resume=run_dir, stages=fake_stages)
    assert calls == ["avatar", "compose"]


def test_partial_artifact_removed_on_failure(cfg, fake_stages):
    def half_written(ctx):
        ctx.path("audio.wav").write_text("partial")
        raise RuntimeError("crash")

    broken = fake_stages[:2] + (Stage("tts", "audio.wav", half_written, TTSError, "script.txt"),) + fake_stages[3:]
    with pytest.raises(TTSError):
        run("t", cfg, stages=broken)
    assert not (next(cfg.outputs_dir.iterdir()) / "audio.wav").exists()


def test_from_stage_reruns_that_stage_and_later(cfg, fake_stages, calls):
    run_dir = run("t", cfg, stages=fake_stages).parent
    calls.clear()
    run("t", cfg, resume=run_dir, from_stage="tts", stages=fake_stages)
    assert calls == ["tts", "avatar", "compose"]


def test_only_stage(cfg, fake_stages, calls):
    run_dir = run("t", cfg, stages=fake_stages).parent
    calls.clear()
    out = run("t", cfg, resume=run_dir, only_stage="script", stages=fake_stages)
    assert calls == ["script"]
    assert out == run_dir / "script.txt"
    assert (run_dir / "final.mp4").exists()  # only_stage never deletes later artifacts


def test_missing_input_artifact_is_a_clear_error(cfg, fake_stages):
    run_dir = cfg.outputs_dir / "empty"
    run_dir.mkdir(parents=True)
    with pytest.raises(PipelineError, match="needs audio.wav"):
        run("t", cfg, resume=run_dir, only_stage="avatar", stages=fake_stages)


def test_audio_and_script_overrides_skip_earlier_stages(cfg, fake_stages, calls, tmp_path):
    wav = tmp_path / "mine.wav"
    wav.write_text("my audio")
    script = tmp_path / "s.txt"
    script.write_text("my script")

    final = run("t", cfg, audio=wav, script_file=script, stages=fake_stages)

    assert calls == ["avatar", "compose"]  # research, script and tts unnecessary
    assert (final.parent / "audio.wav").read_text() == "my audio"
    assert (final.parent / "script.txt").read_text() == "my script"


def test_script_override_still_runs_tts(cfg, fake_stages, calls, tmp_path):
    script = tmp_path / "s.txt"
    script.write_text("my script")
    run("t", cfg, script_file=script, stages=fake_stages)
    assert calls == ["tts", "avatar", "compose"]


def test_bad_arguments(cfg, fake_stages, tmp_path):
    with pytest.raises(PipelineError, match="Unknown stage"):
        run("t", cfg, from_stage="nope", stages=fake_stages)
    with pytest.raises(PipelineError, match="either"):
        run("t", cfg, from_stage="tts", only_stage="tts", stages=fake_stages)
    with pytest.raises(PipelineError, match="does not exist"):
        run("t", cfg, resume=tmp_path / "missing", stages=fake_stages)
    with pytest.raises(PipelineError, match="Override file not found"):
        run("t", cfg, audio=tmp_path / "missing.wav", stages=fake_stages)


def test_no_background_copies_avatar_to_final(tmp_path):
    """The real compose adapter copies (not renames) the avatar when background is disabled."""
    cfg = load_config(environ={"AI_AVATAR__background__enabled": "false", "AI_AVATAR__paths__outputs_dir": str(tmp_path)})
    compose_stage = next(s for s in DEFAULT_STAGES if s.name == "compose")
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    (run_dir / "avatar.mp4").write_bytes(b"video")
    run("t", cfg, resume=run_dir, only_stage="compose", stages=(compose_stage,))
    assert (run_dir / "final.mp4").read_bytes() == b"video"
    assert (run_dir / "avatar.mp4").exists()  # intermediate kept


def test_dry_run_reports_plan_and_checks_without_values(cfg, monkeypatch):
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-super-secret-value")
    plan, checks = dry_run("My Topic", cfg)
    assert plan[0].endswith("-my-topic/")
    assert [p.split(":")[0] for p in plan[1:]] == ["research", "script", "tts", "avatar", "compose"]
    assert all(isinstance(c, Check) for c in checks)
    assert any(c.name == "ffmpeg" for c in checks)
    assert "sk-super-secret-value" not in repr(checks)
    key = next(c for c in checks if c.name == "env OPEN_ROUTER_API_KEY")
    assert key.ok and key.required


def test_slugify():
    assert slugify("  Hello, World! / ünï ") == "hello-world-n"
    assert slugify("!!!") == "topic"
    assert len(slugify("a" * 100)) == 40


def test_failed_forced_rerun_leaves_no_stale_downstream_artifacts(cfg, fake_stages, calls):
    run_dir = run("t", cfg, stages=fake_stages).parent
    fail_tts = Stage("tts", "audio.wav", lambda ctx: (ctx.path("audio.wav").write_text("half"), 1 / 0), TTSError, "script.txt")
    broken = fake_stages[:2] + (fail_tts,) + fake_stages[3:]
    with pytest.raises(TTSError):
        run("t", cfg, resume=run_dir, from_stage="script", stages=broken)
    assert (run_dir / "script.txt").exists()  # re-made before the failure
    for stale in ("audio.wav", "avatar.mp4", "final.mp4"):
        assert not (run_dir / stale).exists()
    calls.clear()
    run("t", cfg, resume=run_dir, stages=fake_stages)  # plain resume finishes the job
    assert calls == ["tts", "avatar", "compose"]


def test_keyboard_interrupt_cleans_partial_artifact_and_records_failure(cfg, fake_stages):
    def interrupted(ctx):
        ctx.path("audio.wav").write_text("half")
        raise KeyboardInterrupt

    stages = fake_stages[:2] + (Stage("tts", "audio.wav", interrupted, TTSError, "script.txt"),) + fake_stages[3:]
    with pytest.raises(KeyboardInterrupt):
        run("t", cfg, stages=stages)
    run_dir = next(cfg.outputs_dir.iterdir())
    assert not (run_dir / "audio.wav").exists()
    assert json.loads((run_dir / "run.json").read_text())["stages"]["tts"]["status"] == "failed"


def test_override_with_resume_invalidates_downstream(cfg, fake_stages, calls, tmp_path):
    run_dir = run("t", cfg, stages=fake_stages).parent
    wav = tmp_path / "new.wav"
    wav.write_text("new audio")
    calls.clear()
    run("t", cfg, resume=run_dir, audio=wav, stages=fake_stages)
    assert calls == ["avatar", "compose"]
    assert (run_dir / "audio.wav").read_text() == "new audio"


def test_override_pointing_at_the_run_dirs_own_file_is_a_noop(cfg, fake_stages, calls):
    run_dir = run("t", cfg, stages=fake_stages).parent
    calls.clear()
    run("t", cfg, resume=run_dir, audio=run_dir / "audio.wav", stages=fake_stages)
    assert calls == []


def test_resume_with_different_topic_is_rejected(cfg, fake_stages):
    run_dir = run("original", cfg, stages=fake_stages).parent
    with pytest.raises(PipelineError, match="original"):
        run("other", cfg, resume=run_dir, stages=fake_stages)


def test_corrupt_run_json_is_a_clear_error(cfg, fake_stages):
    run_dir = run("t", cfg, stages=fake_stages).parent
    (run_dir / "run.json").write_text("{not json")
    with pytest.raises(PipelineError, match="corrupt"):
        run("t", cfg, resume=run_dir, stages=fake_stages)


def test_same_second_same_topic_gets_unique_dirs(cfg, fake_stages, monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 1, 12, 0, 0)

    monkeypatch.setattr("ai_avatar.pipeline.datetime", FrozenDatetime)
    first = run("t", cfg, stages=fake_stages).parent
    second = run("t", cfg, stages=fake_stages).parent
    assert first != second and second.name.endswith("-t-2")


def test_override_validation_happens_before_creating_a_run_dir(cfg, fake_stages, tmp_path):
    with pytest.raises(PipelineError):
        run("t", cfg, audio=tmp_path / "nope.wav", stages=fake_stages)
    assert not cfg.outputs_dir.exists() or not list(cfg.outputs_dir.iterdir())


def test_missing_optional_dependency_gets_an_install_hint(cfg, fake_stages):
    def needs_tts(ctx):
        import definitely_not_installed_tts_pkg  # noqa: F401

    stages = fake_stages[:2] + (Stage("tts", "audio.wav", needs_tts, TTSError, "script.txt", extra="tts"),) + fake_stages[3:]
    with pytest.raises(TTSError, match=r"pip install -e '\.\[tts\]'"):
        run("t", cfg, stages=stages)


def test_unexpected_exceptions_are_wrapped_with_stage_error_type(cfg, fake_stages):
    stages = (Stage("research", "research.json", lambda ctx: 1 / 0, ResearchError),) + fake_stages[1:]
    with pytest.raises(ResearchError, match="research stage failed: division by zero"):
        run("t", cfg, stages=stages)


# --- the real stage adapters, with the heavy functions mocked ---


def test_real_adapters_pass_topic_and_facts_through(cfg, monkeypatch, tmp_path):
    seen = {}

    def fake_run_research(topic, config):
        seen["research_topic"] = topic
        return ResearchBundle(topic=topic, facts=["fact one", "fact two"], freshness="fresh", sources=["rss"])

    def fake_generate_script(topic, facts, config):
        seen["script_args"] = (topic, facts)
        return "the narration"

    monkeypatch.setattr("ai_avatar.research.run_research", fake_run_research)
    monkeypatch.setattr("ai_avatar.stages.script.generate_script", fake_generate_script)

    out = run("black holes", cfg, only_stage="research")
    assert json.loads(out.read_text())["facts"] == ["fact one", "fact two"]
    out = run("black holes", cfg, resume=out.parent, only_stage="script")

    assert seen["research_topic"] == "black holes"
    assert seen["script_args"] == ("black holes", ["fact one", "fact two"])
    assert out.read_text() == "the narration"


def test_real_adapters_wire_tts_avatar_compose_paths(cfg, monkeypatch):
    calls = {}

    def fake_tts(script, output_path, config):
        calls["tts"] = (script, output_path.name, config.tts.voice)
        output_path.write_text("wav")

    def fake_avatar(audio, image, result_dir, config):
        calls["avatar"] = (audio.name, image.name, result_dir.name)
        result_dir.mkdir()
        video = result_dir / "sad.mp4"
        video.write_text("avatar video")
        return video

    def fake_compose(avatar_video, loop_video, output_path, config):
        calls["compose"] = (avatar_video.name, loop_video.name, config.avatar.height_ratio, config.video.width, config.video.height)
        output_path.write_text("final")

    monkeypatch.setattr("ai_avatar.stages.tts.generate_audio", fake_tts)
    monkeypatch.setattr("ai_avatar.stages.avatar.generate_avatar", fake_avatar)
    monkeypatch.setattr("ai_avatar.stages.compose.compose", fake_compose)
    script = cfg.outputs_dir.parent / "s.txt"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("hello world")

    final = run("t", cfg, script_file=script)

    assert final.read_text() == "final"
    assert calls["tts"] == ("hello world", "audio.wav", cfg.tts.voice)
    assert calls["avatar"] == ("audio.wav", Path(cfg.avatar.image).name, "sadtalker")
    assert calls["compose"] == ("avatar.mp4", Path(cfg.background.loop).name, cfg.avatar.height_ratio, 1080, 1920)
    assert (final.parent / "avatar.mp4").read_text() == "avatar video"


def test_secrets_in_exceptions_are_scrubbed_from_run_json_and_error(cfg, fake_stages, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaSyFAKEKEY123456")

    def leaky(ctx):
        raise ConnectionError("Max retries exceeded with url: /customsearch/v1?key=AIzaSyFAKEKEY123456&q=x")

    stages = (Stage("research", "research.json", leaky, ResearchError),) + fake_stages[1:]
    with pytest.raises(ResearchError) as err:
        run("t", cfg, stages=stages)
    run_json = (next(cfg.outputs_dir.iterdir()) / "run.json").read_text()
    for text in (str(err.value), run_json):
        assert "AIzaSyFAKEKEY123456" not in text
        assert "***" in text


def test_scrub_handles_url_credentials_without_env():
    from ai_avatar.redact import scrub

    assert scrub("GET /v1?q=a&key=abc123&x=1") == "GET /v1?q=a&key=***&x=1"
    assert scrub("nothing secret") == "nothing secret"


def test_invalidated_stages_are_removed_from_run_json(cfg, fake_stages):
    run_dir = run("t", cfg, stages=fake_stages).parent
    fail_tts = Stage("tts", "audio.wav", lambda ctx: 1 / 0, TTSError, "script.txt")
    with pytest.raises(TTSError):
        run("t", cfg, resume=run_dir, from_stage="script", stages=fake_stages[:2] + (fail_tts,) + fake_stages[3:])
    stages = json.loads((run_dir / "run.json").read_text())["stages"]
    assert stages["script"]["status"] == "done"
    assert stages["tts"]["status"] == "failed"
    assert "avatar" not in stages and "compose" not in stages


def test_override_that_the_selected_stage_would_overwrite_is_rejected(cfg, fake_stages, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_text("x")
    with pytest.raises(PipelineError, match="can only be combined"):
        run("t", cfg, audio=wav, from_stage="tts", stages=fake_stages)
    with pytest.raises(PipelineError, match="can only be combined"):
        run("t", cfg, audio=wav, only_stage="tts", stages=fake_stages)


def test_impossible_plan_fails_before_touching_anything(cfg, fake_stages):
    run_dir = cfg.outputs_dir / "fresh"
    run_dir.mkdir(parents=True)
    with pytest.raises(PipelineError, match="needs script.txt"):
        run("t", cfg, resume=run_dir, from_stage="tts", stages=fake_stages)
    assert list(run_dir.iterdir()) == []  # no run.json, no copied overrides, nothing deleted


def test_override_must_target_the_stage_it_feeds(cfg, fake_stages, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_text("x")
    script = tmp_path / "s.txt"
    script.write_text("x")
    for kwargs in ({"from_stage": "compose"}, {"only_stage": "compose"}, {"only_stage": "research"}):
        with pytest.raises(PipelineError, match="can only be combined"):
            run("t", cfg, audio=wav, stages=fake_stages, **kwargs)
    with pytest.raises(PipelineError, match="can only be combined"):
        run("t", cfg, script_file=script, only_stage="avatar", stages=fake_stages)
    assert not cfg.outputs_dir.exists() or not list(cfg.outputs_dir.iterdir())  # rejected before touching anything


def test_override_with_its_consumer_stage_is_allowed(cfg, fake_stages, calls, tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_text("x")
    run_dir = run("t", cfg, stages=fake_stages).parent
    calls.clear()
    run("t", cfg, resume=run_dir, audio=wav, from_stage="avatar", stages=fake_stages)
    assert calls == ["avatar", "compose"]


def test_scrub_only_touches_secret_env_vars(monkeypatch):
    from ai_avatar.redact import scrub

    monkeypatch.setenv("OPEN_ROUTER_TITLE", "avatar-demo")
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-or-v1-abcdef123456")
    assert scrub("title avatar-demo key sk-or-v1-abcdef123456") == "title avatar-demo key ***"


def test_logging_filter_scrubs_urls(capsys):
    import logging

    from ai_avatar.logging_setup import setup_logging

    logging.getLogger().handlers.clear()
    setup_logging(1)
    logging.getLogger("urllib3.connectionpool").debug("GET %s", "/customsearch/v1?key=SECRETVALUE99&q=x")
    err = capsys.readouterr().err
    assert "SECRETVALUE99" not in err and "key=***" in err
    logging.getLogger().handlers.clear()


@pytest.mark.parametrize(
    "kwargs, existing",
    [
        ({}, []),
        ({}, ["research.json"]),
        ({}, ["research.json", "script.txt", "audio.wav"]),
        ({}, ["avatar.mp4"]),
        ({}, ["research.json", "script.txt", "audio.wav", "avatar.mp4", "final.mp4"]),
        ({"from_stage": "script"}, ["research.json", "script.txt", "audio.wav", "avatar.mp4", "final.mp4"]),
        ({"only_stage": "tts"}, ["script.txt"]),
        ({"only_stage": "compose"}, ["avatar.mp4"]),
        ({"script_file": "S"}, []),
        ({"script_file": "S"}, ["research.json", "script.txt", "audio.wav", "avatar.mp4", "final.mp4"]),
        ({"audio": "A"}, ["research.json", "script.txt"]),
        ({"audio": "A", "script_file": "S"}, []),
        ({"audio": "A", "from_stage": "avatar"}, ["audio.wav", "avatar.mp4", "final.mp4"]),
    ],
)
def test_planned_stages_matches_what_run_actually_does(cfg, fake_stages, calls, tmp_path, kwargs, existing):
    """The dry-run planner must agree with run() or the dry-run would lie."""
    from ai_avatar.pipeline import planned_stages

    src = {"A": tmp_path / "a.wav", "S": tmp_path / "s.txt"}
    for p in src.values():
        p.write_text("x")
    kwargs = {k: src[v] if v in src else v for k, v in kwargs.items()}
    run_dir = cfg.outputs_dir / "r"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({"topic": "t"}))
    for name in existing:
        (run_dir / name).write_text("x")

    expected = planned_stages(fake_stages, run_dir=run_dir, **kwargs)
    run("t", cfg, resume=run_dir, stages=fake_stages, **kwargs)
    assert calls == expected


def test_validate_options_has_no_side_effects(cfg, fake_stages, tmp_path):
    from ai_avatar.pipeline import validate_options

    validate_options(fake_stages, resume=None, from_stage="tts", audio=None, script_file=None)
    with pytest.raises(PipelineError, match="does not exist"):
        validate_options(fake_stages, resume=tmp_path / "nope")


@pytest.mark.parametrize(
    "kwargs, existing, error",
    [
        ({"from_stage": "tts"}, ["research.json"], "needs script.txt"),
        ({"only_stage": "avatar"}, ["script.txt"], "needs audio.wav"),
        ({"only_stage": "compose"}, [], "needs avatar.mp4"),
    ],
)
def test_planner_rejects_stages_whose_input_will_be_missing(cfg, fake_stages, kwargs, existing, error):
    from ai_avatar.pipeline import planned_stages

    run_dir = cfg.outputs_dir / "r"
    run_dir.mkdir(parents=True)
    for name in existing:
        (run_dir / name).write_text("x")
    with pytest.raises(PipelineError, match=error):
        planned_stages(fake_stages, run_dir=run_dir, **kwargs)
    with pytest.raises(PipelineError, match=error):  # and run() agrees, before changing anything
        run("t", cfg, resume=run_dir, stages=fake_stages, **kwargs)
    assert {p.name for p in run_dir.iterdir()} == set(existing)


def test_planner_checks_topic_and_run_json_like_run(cfg, fake_stages):
    from ai_avatar.pipeline import planned_stages

    run_dir = run("original", cfg, stages=fake_stages).parent
    with pytest.raises(PipelineError, match="original"):
        planned_stages(fake_stages, topic="other", run_dir=run_dir)
    (run_dir / "run.json").write_text("{bad")
    with pytest.raises(PipelineError, match="corrupt"):
        planned_stages(fake_stages, topic="original", run_dir=run_dir)


def test_override_that_is_the_run_dirs_own_file_plans_nothing(cfg, fake_stages):
    from ai_avatar.pipeline import planned_stages

    run_dir = run("t", cfg, stages=fake_stages).parent
    assert planned_stages(fake_stages, run_dir=run_dir, audio=run_dir / "audio.wav") == []
