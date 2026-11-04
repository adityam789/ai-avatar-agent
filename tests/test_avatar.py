"""Avatar stage with SadTalker mocked: validation, option mapping, output detection, offline fake."""

import os
import sys
import textwrap

import pytest
from ffmpeg_media import make_image, requires_ffmpeg

from ai_avatar.config import load_config
from ai_avatar.errors import AvatarError
from ai_avatar.stages import avatar as avatar_mod
from ai_avatar.stages.avatar import generate_avatar, missing_sadtalker_files

MAPPING_NETS = ("mapping_00109-model.pth.tar", "mapping_00229-model.pth.tar")


@pytest.fixture
def env(tmp_path):
    """A project root with a (fake) checked-out SadTalker, checkpoints, an image and a wav."""
    cfg = load_config(environ={})
    cfg.root = tmp_path
    sad = tmp_path / "models" / "sad_talker"
    (sad / "src" / "config").mkdir(parents=True)
    (sad / "checkpoints").mkdir()
    (sad / "inference.py").write_text("def run(**kwargs):\n    pass\n")
    for name in ("SadTalker_V0.0.2_256.safetensors", "SadTalker_V0.0.2_512.safetensors", *MAPPING_NETS):
        (sad / "checkpoints" / name).write_text("weights")
    image, audio = tmp_path / "me.png", tmp_path / "audio.wav"
    image.write_text("png")
    audio.write_text("wav")
    return cfg, image, audio, tmp_path / "run" / "sadtalker"


def stub_sadtalker(monkeypatch, filename="2026_11_03_10.00.00.mp4", write=True):
    """Replace the real SadTalker call; it records options and (like the real one) writes <timestamp>.mp4."""
    seen = {}

    def fake_run(cfg, **options):
        seen.update(options)
        if write:
            (avatar_mod.Path(options["result_dir"]) / filename).write_text("video")

    monkeypatch.setattr(avatar_mod, "_run_sadtalker", fake_run)
    return seen


def test_options_are_mapped_and_paths_are_absolute(env, monkeypatch, tmp_path):
    cfg, image, audio, result_dir = env
    cfg.avatar.size, cfg.avatar.pose_style, cfg.avatar.expression_scale = 512, 3, 1.4
    cfg.avatar.still, cfg.avatar.preprocess = False, "crop"
    seen = stub_sadtalker(monkeypatch)
    monkeypatch.chdir(tmp_path)
    relative_result_dir = result_dir.relative_to(tmp_path)

    out = generate_avatar(audio.relative_to(tmp_path), image.relative_to(tmp_path), relative_result_dir, cfg)

    assert seen == {
        "driven_audio": str(audio), "source_image": str(image), "result_dir": str(result_dir),
        "checkpoint_dir": str(tmp_path / "models/sad_talker/checkpoints"),
        "size": 512, "enhancer": None, "pose_style": 3, "expression_scale": 1.4, "still": False, "preprocess": "crop",
    }  # fmt: skip
    assert out == result_dir / "2026_11_03_10.00.00.mp4"


def test_defaults_match_the_documented_talking_head_setup(env, monkeypatch):
    cfg, image, audio, result_dir = env
    seen = stub_sadtalker(monkeypatch)
    generate_avatar(audio, image, result_dir, cfg)
    assert (seen["size"], seen["enhancer"], seen["still"], seen["preprocess"]) == (256, None, True, "full")


def test_gfpgan_enhancer_needs_its_weights(env, monkeypatch):
    cfg, image, audio, result_dir = env
    cfg.avatar.enhancer = "gfpgan"
    seen = stub_sadtalker(monkeypatch)
    with pytest.raises(AvatarError, match=r"gfpgan/weights/GFPGANv1\.4\.pth.*download_models\.sh"):
        generate_avatar(audio, image, result_dir, cfg)
    weights = cfg.sadtalker_dir / "gfpgan" / "weights" / "GFPGANv1.4.pth"
    weights.parent.mkdir(parents=True)
    weights.write_text("w")
    generate_avatar(audio, image, result_dir, cfg)
    assert seen["enhancer"] == "gfpgan"


def test_only_the_new_video_is_returned(env, monkeypatch):
    cfg, image, audio, result_dir = env
    result_dir.mkdir(parents=True)
    (result_dir / "9999_old_run.mp4").write_text("old")  # sorts after the new name: must not be picked
    stub_sadtalker(monkeypatch, filename="2026_11_03_10.00.00.mp4")
    assert generate_avatar(audio, image, result_dir, cfg).name == "2026_11_03_10.00.00.mp4"


def test_a_rewritten_file_with_the_same_name_counts_as_new(env, monkeypatch):
    cfg, image, audio, result_dir = env
    result_dir.mkdir(parents=True)
    stale = result_dir / "same.mp4"
    stale.write_text("old")
    os.utime(stale, ns=(1_000_000_000, 1_000_000_000))
    stub_sadtalker(monkeypatch, filename="same.mp4")
    assert generate_avatar(audio, image, result_dir, cfg) == stale


def test_no_new_video_points_at_face_detection(env, monkeypatch):
    cfg, image, audio, result_dir = env
    stub_sadtalker(monkeypatch, write=False)
    with pytest.raises(AvatarError, match="wrote no video.*face"):
        generate_avatar(audio, image, result_dir, cfg)


def test_sadtalker_crash_becomes_a_scrubbed_avatar_error(env, monkeypatch):
    cfg, image, audio, result_dir = env
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaSyFAKEKEY123456")

    def crash(cfg, **options):
        raise RuntimeError("CUDA error key=AIzaSyFAKEKEY123456")

    monkeypatch.setattr(avatar_mod, "_run_sadtalker", crash)
    with pytest.raises(AvatarError) as exc:
        generate_avatar(audio, image, result_dir, cfg)
    assert "SadTalker failed: CUDA error" in str(exc.value) and "AIzaSyFAKEKEY123456" not in str(exc.value)


def test_input_validation_messages(env, monkeypatch):
    cfg, image, audio, result_dir = env
    stub_sadtalker(monkeypatch)
    with pytest.raises(AvatarError, match="source image not found"):
        generate_avatar(audio, image.with_name("nope.png"), result_dir, cfg)
    with pytest.raises(AvatarError, match="Audio not found"):
        generate_avatar(audio.with_name("nope.wav"), image, result_dir, cfg)

    (cfg.sadtalker_checkpoints / "SadTalker_V0.0.2_256.safetensors").unlink()
    assert [p.name for p in missing_sadtalker_files(cfg)] == ["SadTalker_V0.0.2_256.safetensors"]
    with pytest.raises(AvatarError, match=r"SadTalker_V0\.0\.2_256\.safetensors.*scripts/download_models\.sh"):
        generate_avatar(audio, image, result_dir, cfg)

    (cfg.sadtalker_dir / "inference.py").unlink()
    with pytest.raises(AvatarError, match="git submodule update --init"):
        generate_avatar(audio, image, result_dir, cfg)


def test_required_checkpoints_follow_size_and_preprocess(env):
    cfg = env[0]
    assert missing_sadtalker_files(cfg) == []
    (cfg.sadtalker_checkpoints / MAPPING_NETS[1]).unlink()
    assert missing_sadtalker_files(cfg) == []  # preprocess "full" uses the 00109 net
    cfg.avatar.preprocess = "crop"
    assert [p.name for p in missing_sadtalker_files(cfg)] == [MAPPING_NETS[1]]
    (cfg.sadtalker_checkpoints / "SadTalker_V0.0.2_512.safetensors").unlink()
    cfg.avatar.size = 512
    assert len(missing_sadtalker_files(cfg)) == 2


@pytest.fixture
def clean_modules():
    names = ("models", "models.sad_talker", "models.sad_talker.inference")
    saved = {n: sys.modules.pop(n, None) for n in names}
    yield
    for n in names:
        sys.modules.pop(n, None)
        if saved[n] is not None:
            sys.modules[n] = saved[n]


def test_run_sadtalker_imports_from_the_submodule_with_the_context_active(env, clean_modules, tmp_path):
    cfg, *_ = env
    cfg.avatar.enhancer = "gfpgan"
    (cfg.sadtalker_dir / "inference.py").write_text(
        textwrap.dedent("""
        import os, sys
        seen = {}
        def run(**kwargs):
            seen.update(kwargs, argv0=sys.argv[0], cwd=os.getcwd())
    """)
    )
    cwd, argv0 = os.getcwd(), sys.argv[0]
    avatar_mod._run_sadtalker(cfg, size=256, enhancer="gfpgan")
    seen = sys.modules["models.sad_talker.inference"].seen
    assert seen["size"] == 256 and seen["argv0"].startswith(str(tmp_path))
    assert seen["cwd"] == str(cfg.sadtalker_dir.resolve())  # GFPGAN looks for gfpgan/weights in the CWD
    assert (os.getcwd(), sys.argv[0]) == (cwd, argv0)  # restored


def test_missing_python_dependency_gives_install_hint(env, clean_modules):
    cfg, *_ = env
    (cfg.sadtalker_dir / "inference.py").write_text("import a_module_that_is_not_installed_xyz\n")
    with pytest.raises(AvatarError, match=r"a_module_that_is_not_installed_xyz.*pip install -e '\.\[avatar\]'"):
        avatar_mod._run_sadtalker(cfg)


# --- offline fake (real ffmpeg) ---


@requires_ffmpeg
def test_fake_avatar_renders_still_image_and_audio_into_an_mp4(tmp_path):
    from ffmpeg_media import probe

    from ai_avatar.stages.tts import generate_audio

    cfg = load_config(environ={})
    cfg.offline = True  # no checkpoints or submodule needed
    image = make_image(tmp_path / "me.png", "120x200")
    audio = generate_audio("one two three four five", tmp_path / "audio.wav", cfg)  # 2 s
    out = generate_avatar(audio, image, tmp_path / "sadtalker", cfg)
    info = probe(out)
    assert out.parent == (tmp_path / "sadtalker").resolve() and out.suffix == ".mp4"
    assert info["video"]["codec_name"] == "h264" and info["audio"] is not None
    assert (info["video"]["width"], info["video"]["height"]) == (154, 256)  # fits 256x256, aspect kept, even
    assert info["duration"] == pytest.approx(2.0, abs=0.3)
