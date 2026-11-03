"""Typed exceptions. Each carries an actionable, user-facing message."""


class AiAvatarError(Exception):
    """Base class for expected failures (the CLI prints these without a traceback)."""


class ConfigError(AiAvatarError):
    """Invalid or missing configuration."""


class PipelineError(AiAvatarError):
    """Misuse of the pipeline (bad stage name, missing input artifact, ...)."""


class ResearchError(AiAvatarError):
    """No usable research could be gathered."""


class LLMError(AiAvatarError):
    """The language-model call failed or returned something unusable."""


class TTSError(AiAvatarError):
    """Speech synthesis failed."""


class AvatarError(AiAvatarError):
    """Talking-head rendering failed."""


class ComposeError(AiAvatarError):
    """The ffmpeg compositing step failed."""
