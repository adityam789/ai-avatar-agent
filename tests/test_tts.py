"""TTS stage: device resolution, lazy cached model loading, voice options, output verification."""

import subprocess
import sys
import types
import wave
from pathlib import Path

import pytest
from ffmpeg_media import requires_ffmpeg

from ai_avatar.config import load_config
from ai_avatar.errors import TTSError
from ai_avatar.stages import tts
from ai_avatar.stages.fakes import FakeTTS
from ai_avatar.stages.tts import resolve_device, wav_duration, xtts_device


@pytest.mark.parametrize(
    ("requested", "cuda", "mps", "expected"),
    [
        ("auto", True, True, "cuda"),
        ("auto", False, True, "mps"),
        ("auto", False, False, "cpu"),
        ("cpu", True, True, "cpu"),
        ("cuda", True, False, "cuda"),
        ("mps", False, True, "mps"),
    ],
)
def test_resolve_device(requested, cuda, mps, expected):
    assert resolve_device(requested, cuda=cuda, mps=mps) == expected


@pytest.mark.parametrize("requested", ["cuda", "mps"])
def test_explicit_missing_accelerator_is_an_error(requested):
    with pytest.raises(TTSError, match=requested):
        resolve_device(requested, cuda=False, mps=False)


def test_xtts_falls_back_from_mps_to_cpu_with_a_warning(caplog):
    with caplog.at_level("WARNING"):
        assert xtts_device("auto", cuda=False, mps=True) == "cpu"
        assert xtts_device("mps", cuda=False, mps=True) == "cpu"
    assert "MPS" in caplog.text
    caplog.clear()
    assert xtts_device("auto", cuda=True, mps=True) == "cuda" and xtts_device("cpu", cuda=False, mps=False) == "cpu"
    assert not caplog.records


def test_importing_the_stage_does_not_import_torch_or_tts():
    code = "import sys, ai_avatar.stages.tts; assert not {'torch', 'TTS'} & set(sys.modules), sorted(sys.modules)"
    subprocess.run([sys.executable, "-c", code], check=True)


@pytest.fixture
def fake_coqui(monkeypatch):
    """A stand-in `TTS.api` module that counts model loads."""
    loads = []

    class FakeModel:
        def __init__(self, name):
            loads.append(("init", name))

        def to(self, device):
            loads.append(("to", device))
            return self

    package, api = types.ModuleType("TTS"), types.ModuleType("TTS.api")
    api.TTS = FakeModel
    monkeypatch.setitem(sys.modules, "TTS", package)
    monkeypatch.setitem(sys.modules, "TTS.api", api)
    tts.get_tts.cache_clear()
    yield loads
    tts.get_tts.cache_clear()


def test_get_tts_loads_once_per_device_and_caches(fake_coqui):
    first = tts.get_tts("cpu")
    assert tts.get_tts("cpu") is first
    assert fake_coqui == [("init", tts.MODEL_NAME), ("to", "cpu")]


def test_missing_coqui_package_gives_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "TTS.api", None)  # makes `from TTS.api import TTS` raise ImportError
    tts.get_tts.cache_clear()
    with pytest.raises(TTSError, match=r"coqui-tts.*pip install -e '\.\[tts\]'"):
        tts.get_tts("cpu")


def test_model_load_failures_are_scrubbed(monkeypatch, fake_coqui):
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaSyFAKEKEY123456")
    sys.modules["TTS.api"].TTS = lambda name: (_ for _ in ()).throw(OSError("GET /m?key=AIzaSyFAKEKEY123456 failed"))
    with pytest.raises(TTSError) as exc:
        tts.get_tts("cpu")
    assert "AIzaSyFAKEKEY123456" not in str(exc.value) and "Could not load XTTS v2" in str(exc.value)


def test_model_load_failure_hints_at_the_licence_prompt(fake_coqui):
    sys.modules["TTS.api"].TTS = lambda name: (_ for _ in ()).throw(EOFError("EOF when reading a line"))
    with pytest.raises(TTSError, match=r"COQUI_TOS_AGREED=1.*non-commercial|non-commercial.*COQUI_TOS_AGREED=1"):
        tts.get_tts("cpu")


# --- generate_audio ---


def write_wav(path, seconds=1.0, rate=8000):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(b"\x00\x00" * int(rate * seconds))


class RecordingBackend:
    def __init__(self, behaviour=None):
        self.calls, self.behaviour = [], behaviour

    def tts_to_file(self, **kwargs):
        self.calls.append(kwargs)
        (self.behaviour or (lambda kw: write_wav(kw["file_path"])))(kwargs)


@pytest.fixture
def cfg(tmp_path):
    cfg = load_config(environ={})
    cfg.root = tmp_path
    return cfg


@pytest.fixture
def backend(monkeypatch):
    """Replace the real model with a recorder; records the device the model was requested on."""
    holder = types.SimpleNamespace(backend=RecordingBackend(), devices=[])
    monkeypatch.setattr(tts, "get_tts", lambda device: holder.devices.append(device) or holder.backend)
    monkeypatch.setattr(tts, "_accelerators", lambda: (False, True))  # Apple silicon: MPS only
    return holder


def test_generate_audio_passes_voice_language_and_resolves_device(backend, cfg, tmp_path):
    cfg.tts.voice, cfg.tts.language = "Claribel Dervla", "fr"
    out = tts.generate_audio("Bonjour le monde", tmp_path / "run" / "audio.wav", cfg)
    assert out == tmp_path / "run" / "audio.wav" and out.is_file()
    assert backend.backend.calls == [
        {"text": "Bonjour le monde", "file_path": str(out), "language": "fr", "speaker": "Claribel Dervla"}
    ]
    assert backend.devices == ["cpu"]  # auto -> mps -> XTTS falls back to cpu


def test_speaker_wav_replaces_the_builtin_voice(backend, cfg, tmp_path):
    reference = tmp_path / "me.wav"
    write_wav(reference)
    cfg.tts.speaker_wav = reference
    tts.generate_audio("hello there", tmp_path / "a.wav", cfg)
    call = backend.backend.calls[0]
    assert call["speaker_wav"] == str(reference) and "speaker" not in call


def test_missing_speaker_wav_is_an_error(backend, cfg, tmp_path):
    cfg.tts.speaker_wav = tmp_path / "nope.wav"
    with pytest.raises(TTSError, match="speaker_wav not found"):
        tts.generate_audio("hello", tmp_path / "a.wav", cfg)
    assert not backend.backend.calls


def test_empty_script_is_rejected(backend, cfg, tmp_path):
    with pytest.raises(TTSError, match="empty"):
        tts.generate_audio("  \n", tmp_path / "a.wav", cfg)


def test_backend_exceptions_become_scrubbed_tts_errors(backend, cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaSyFAKEKEY123456")

    def boom(kwargs):
        raise RuntimeError("CUDA out of memory (key=AIzaSyFAKEKEY123456)")

    backend.backend.behaviour = boom
    with pytest.raises(TTSError) as exc:
        tts.generate_audio("hello", tmp_path / "a.wav", cfg)
    assert "out of memory" in str(exc.value) and "AIzaSyFAKEKEY123456" not in str(exc.value)


def test_output_is_verified(backend, cfg, tmp_path):
    out = tmp_path / "a.wav"
    backend.backend.behaviour = lambda kw: None
    with pytest.raises(TTSError, match="was not written"):
        tts.generate_audio("hello", out, cfg)
    backend.backend.behaviour = lambda kw: write_wav(kw["file_path"], seconds=0)
    with pytest.raises(TTSError, match="empty audio"):
        tts.generate_audio("hello", out, cfg)
    backend.backend.behaviour = lambda kw: write_bytes(kw["file_path"], b"not a wav file at all")
    with pytest.raises(TTSError, match="not a readable PCM wav"):
        tts.generate_audio("hello", out, cfg)


def write_bytes(path, data):
    Path(path).write_bytes(data)


def test_a_stale_output_file_does_not_pass_the_written_check(backend, cfg, tmp_path):
    out = tmp_path / "a.wav"
    write_wav(out, seconds=3)  # left over from an earlier run
    backend.backend.behaviour = lambda kw: None  # synthesis "succeeds" but writes nothing
    with pytest.raises(TTSError, match="was not written"):
        tts.generate_audio("hello", out, cfg)
    assert not out.exists()


@pytest.mark.parametrize(
    ("content", "message"),
    [(None, "empty audio"), (b"not a wav file at all", "not a readable PCM wav")],
)
def test_rejected_output_is_not_left_on_disk(backend, cfg, tmp_path, content, message):
    out = tmp_path / "a.wav"
    if content is None:
        backend.backend.behaviour = lambda kw: write_wav(kw["file_path"], seconds=0)
    else:
        backend.backend.behaviour = lambda kw: write_bytes(kw["file_path"], content)
    with pytest.raises(TTSError, match=message):
        tts.generate_audio("hello", out, cfg)
    assert not out.exists()


# --- wav formats the stdlib cannot read ---


def _ffmpeg_wav(path, codec, *extra):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=1.5:sample_rate=16000",
         "-c:a", codec, *extra, str(path)],
        check=True,
    )  # fmt: skip


@requires_ffmpeg
@pytest.mark.parametrize("codec", ["pcm_f32le", "pcm_s24le"])  # IEEE float / WAVE_FORMAT_EXTENSIBLE
def test_wav_duration_reads_wavs_the_stdlib_rejects_via_ffprobe(tmp_path, codec):
    path = tmp_path / "x.wav"
    _ffmpeg_wav(path, codec)
    with pytest.raises(wave.Error), wave.open(str(path), "rb"):
        pass
    assert wav_duration(path) == pytest.approx(1.5, abs=0.05)


@requires_ffmpeg
def test_float_wav_from_the_backend_is_accepted(backend, cfg, tmp_path):
    backend.backend.behaviour = lambda kw: _ffmpeg_wav(kw["file_path"], "pcm_f32le")
    out = tts.generate_audio("hello", tmp_path / "a.wav", cfg)
    assert out.is_file()


@requires_ffmpeg
def test_corrupt_wav_is_still_a_tts_error(tmp_path):
    path = tmp_path / "bad.wav"
    path.write_bytes(b"RIFF....WAVEgarbage")
    with pytest.raises(TTSError, match="not a readable PCM wav"):
        wav_duration(path)


def test_unreadable_wav_without_ffprobe_is_a_tts_error(tmp_path, monkeypatch):
    monkeypatch.setattr(tts.shutil, "which", lambda name: None)
    path = tmp_path / "bad.wav"
    path.write_bytes(b"nope")
    with pytest.raises(TTSError, match="ffprobe is not installed"):
        wav_duration(path)


def test_nan_duration_from_ffprobe_fallback_is_rejected(backend, cfg, tmp_path, monkeypatch):
    backend.backend.behaviour = lambda kw: write_bytes(kw["file_path"], b"float wav the stdlib rejects")
    monkeypatch.setattr(tts.shutil, "which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(tts, "probe_duration", lambda path: float("nan"))
    with pytest.raises(TTSError, match="empty audio"):
        tts.generate_audio("hello", tmp_path / "a.wav", cfg)
    assert not (tmp_path / "a.wav").exists()


# --- offline fake ---


def test_offline_uses_fake_tts_without_touching_the_model(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "get_tts", lambda device: pytest.fail("offline must not load a model"))
    cfg.offline = True
    short = tts.generate_audio(" ".join(["w"] * 5), tmp_path / "short.wav", cfg)
    long = tts.generate_audio(" ".join(["w"] * 50), tmp_path / "long.wav", cfg)
    assert wav_duration(short) == pytest.approx(2.0, abs=0.01)
    assert wav_duration(long) == pytest.approx(20.0, abs=0.01)


def test_fake_tts_has_a_minimum_length_and_accepts_voice_options(tmp_path):
    FakeTTS().tts_to_file(text="hi", file_path=str(tmp_path / "x.wav"), language="en", speaker_wav="ref.wav")
    assert wav_duration(tmp_path / "x.wav") == pytest.approx(0.5, abs=0.01)


def test_partial_file_is_removed_when_synthesis_raises(tmp_path, monkeypatch):
    from ai_avatar.config import load_config
    from ai_avatar.errors import TTSError
    from ai_avatar.stages import tts

    class Crashing:
        def tts_to_file(self, text, file_path, **kwargs):
            Path(file_path).write_bytes(b"RIFF-partial")
            raise RuntimeError("boom")

    monkeypatch.setattr(tts, "get_tts", lambda device: Crashing())
    monkeypatch.setattr(tts, "_accelerators", lambda: (False, False))
    out = tmp_path / "audio.wav"
    with pytest.raises(TTSError, match="Speech synthesis failed"):
        tts.generate_audio("hello there", out, load_config(environ={}))
    assert not out.exists()
