"""Real-ffmpeg tests: compose a playable 1080x1920 video and run the offline fakes end to end."""

import time

from ffmpeg_media import make_image, make_video, probe, requires_ffmpeg

from ai_avatar import pipeline
from ai_avatar.config import load_config
from ai_avatar.stages.avatar import generate_avatar
from ai_avatar.stages.compose import compose
from ai_avatar.stages.tts import generate_audio, wav_duration

pytestmark = requires_ffmpeg


def _assert_final_video(path, expected_seconds):
    info = probe(path)
    assert (info["video"]["width"], info["video"]["height"]) == (1080, 1920)
    assert info["video"]["codec_name"] == "h264" and info["video"]["pix_fmt"] == "yuv420p"
    assert info["audio"] is not None and info["audio"]["codec_name"] == "aac"
    assert abs(info["duration"] - expected_seconds) < 0.3
    assert abs(float(info["video"]["duration"]) - expected_seconds) < 0.3  # the background loop filled it all


def test_compose_writes_a_playable_1080x1920_video_and_loops_the_background(tmp_path):
    cfg = load_config(environ={})
    avatar = make_video(tmp_path / "avatar.mp4", seconds=2, audio=True)
    loop = make_video(tmp_path / "loop.mp4", seconds=0.5, size="320x180")  # shorter than the audio: must loop
    out = tmp_path / "final.mp4"
    compose(avatar, loop, out, cfg)
    _assert_final_video(out, expected_seconds=2)
    assert probe(out)["video"]["nb_frames"] != "0"


def test_offline_fakes_run_end_to_end(tmp_path):
    cfg = load_config(environ={})
    cfg.offline = True
    cfg.avatar.image = make_image(tmp_path / "me.png")  # non-square on purpose
    loop = make_video(tmp_path / "loop.mp4", seconds=1, size="320x180")
    script = "one two three four five six seven eight nine ten"  # 10 words -> 4 s of fake speech

    started = time.perf_counter()
    audio = generate_audio(script, tmp_path / "audio.wav", cfg)
    avatar = generate_avatar(audio, cfg.avatar.image, tmp_path / "sadtalker", cfg)
    compose(avatar, loop, tmp_path / "final.mp4", cfg)
    assert time.perf_counter() - started < 20

    assert abs(wav_duration(audio) - 4.0) < 0.01
    assert avatar.parent == (tmp_path / "sadtalker").resolve() and avatar.suffix == ".mp4"
    _assert_final_video(tmp_path / "final.mp4", expected_seconds=4)


def test_offline_pipeline_from_the_tts_stage_produces_final_mp4(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_AVATAR__paths__outputs_dir", str(tmp_path / "out"))
    cfg = load_config()
    cfg.offline = True
    cfg.avatar.image = make_image(tmp_path / "me.png")
    cfg.background.loop = make_video(tmp_path / "loop.mp4", seconds=1, size="320x180")
    script = tmp_path / "script.txt"
    script.write_text("a short offline narration for the pipeline")

    final = pipeline.run("demo", cfg, script_file=script)  # research/script already satisfied by the override

    assert final.name == "final.mp4"
    _assert_final_video(final, expected_seconds=wav_duration(final.parent / "audio.wav"))
    assert (final.parent / "avatar.mp4").is_file()


def test_full_range_avatar_input_still_yields_plain_yuv420p(tmp_path):
    """SadTalker/FakeAvatar write full-range yuvj420p; the output must be limited-range yuv420p."""
    from ffmpeg_media import _ffmpeg

    cfg = load_config(environ={})
    avatar = tmp_path / "avatar.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=160x160:rate=10:duration=1", "-f", "lavfi", "-i",
            "sine=frequency=440:sample_rate=16000:duration=1", "-c:v", "libx264", "-pix_fmt", "yuvj420p",
            "-c:a", "aac", avatar)  # fmt: skip
    assert probe(avatar)["video"]["pix_fmt"] == "yuvj420p"
    loop = make_video(tmp_path / "loop.mp4", seconds=1, size="320x180")
    compose(avatar, loop, tmp_path / "final.mp4", cfg)
    assert probe(tmp_path / "final.mp4")["video"]["pix_fmt"] == "yuv420p"
