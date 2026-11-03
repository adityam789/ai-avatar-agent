"""Text-to-speech stage using Coqui XTTS v2 (``coqui-tts`` package, ``tts`` extra).

The model is loaded lazily on first use (importing this module needs neither torch nor ``TTS``)
and cached for the life of the process. With ``cfg.offline`` a silent :class:`FakeTTS` is used
instead, so nothing is downloaded and no GPU is needed.

Licence: the XTTS v2 *weights* are under the Coqui Public Model License (non-commercial use only);
the first download asks you to accept it (set ``COQUI_TOS_AGREED=1`` once you have read it to skip
the prompt in non-interactive runs).
"""

from __future__ import annotations

import logging
import wave
from functools import lru_cache
from pathlib import Path

from ai_avatar.config import Config
from ai_avatar.errors import TTSError
from ai_avatar.redact import scrub

log = logging.getLogger(__name__)

MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"


def resolve_device(requested: str, *, cuda: bool, mps: bool) -> str:
    """Pick the torch device for ``requested`` (``auto``/``cpu``/``cuda``/``mps``): auto = cuda > mps > cpu.

    Pure: availability is passed in. An explicitly requested accelerator that is missing is an error,
    not a silent downgrade.
    """
    if requested == "auto":
        return "cuda" if cuda else "mps" if mps else "cpu"
    if requested == "cuda" and not cuda:
        raise TTSError("tts.device is 'cuda' but CUDA is not available. Use 'auto' or 'cpu'.")
    if requested == "mps" and not mps:
        raise TTSError("tts.device is 'mps' but Apple MPS is not available. Use 'auto' or 'cpu'.")
    return requested


def xtts_device(requested: str, *, cuda: bool, mps: bool) -> str:
    """:func:`resolve_device`, except that MPS falls back to cpu (XTTS v2 is unreliable on MPS)."""
    device = resolve_device(requested, cuda=cuda, mps=mps)
    if device == "mps":
        log.warning("XTTS v2 is unreliable on Apple MPS (unsupported ops, garbled audio); using cpu instead.")
        return "cpu"
    return device


def _accelerators() -> tuple[bool, bool]:
    """``(cuda_available, mps_available)``; ``(False, False)`` when torch is not installed."""
    try:
        import torch
    except ImportError:
        return False, False
    mps = getattr(torch.backends, "mps", None)
    return torch.cuda.is_available(), bool(mps and mps.is_available())


@lru_cache(maxsize=1)
def get_tts(device: str):
    """Load XTTS v2 onto ``device`` once per process (the first call can download ~2 GB)."""
    try:
        from TTS.api import TTS  # heavy; provided by the `tts` extra (package: coqui-tts)
    except ImportError as exc:
        raise TTSError("The 'coqui-tts' package is not installed. Install it with: pip install -e '.[tts]'") from exc
    log.info("Loading XTTS v2 on %s (first run downloads the model)", device)
    try:
        return TTS(MODEL_NAME).to(device)
    except Exception as exc:  # download failure, licence prompt without a TTY, corrupt cache, ...
        raise TTSError(f"Could not load XTTS v2 on {device}: {scrub(exc)}") from exc


def wav_duration(path: Path) -> float:
    """Length of a PCM wav file in seconds."""
    with wave.open(str(path), "rb") as f:
        return f.getnframes() / f.getframerate()


def generate_audio(script: str, output_path: Path, cfg: Config) -> Path:
    """Synthesize ``script`` into the wav file ``output_path`` and return it.

    Uses ``cfg.tts.speaker_wav`` (voice cloning from a reference clip) when set, otherwise the built-in
    ``cfg.tts.voice``. Raises :class:`TTSError` if synthesis fails or the result is missing or empty.
    """
    if not script.strip():
        raise TTSError("The script is empty; nothing to synthesize.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    voice: dict[str, str] = {"speaker": cfg.tts.voice}
    if cfg.tts.speaker_wav is not None:
        reference = cfg.resolve(cfg.tts.speaker_wav)
        if not reference.is_file():
            raise TTSError(f"tts.speaker_wav not found: {reference}. Point it at a ~6-30 s clean speech clip.")
        voice = {"speaker_wav": str(reference)}

    if cfg.offline:
        from ai_avatar.stages.fakes import FakeTTS

        tts = FakeTTS()
    else:
        cuda, mps = _accelerators()
        tts = get_tts(xtts_device(cfg.tts.device, cuda=cuda, mps=mps))
    try:
        tts.tts_to_file(text=script, file_path=str(output_path), language=cfg.tts.language, **voice)
    except TTSError:
        raise
    except Exception as exc:
        raise TTSError(f"Speech synthesis failed: {scrub(exc)}") from exc

    if not output_path.is_file():
        raise TTSError(f"Speech synthesis finished but {output_path} was not written.")
    try:
        seconds = wav_duration(output_path)
    except (wave.Error, EOFError, ZeroDivisionError) as exc:
        raise TTSError(f"{output_path} is not a readable PCM wav file ({exc}).") from exc
    if seconds <= 0:
        raise TTSError(f"Speech synthesis produced an empty audio file: {output_path}")
    log.info("Synthesized %.1fs of audio -> %s", seconds, output_path)
    return output_path
