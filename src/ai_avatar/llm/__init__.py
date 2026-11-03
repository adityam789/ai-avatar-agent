"""LLM access. Stages call ``build_llm(cfg)`` and then ``llm(prompt) -> str``."""

from ai_avatar.config import Config


def build_llm(cfg: Config):
    """Return a callable ``llm(prompt: str) -> str`` for the configured endpoint (Task 07 adds fallbacks/offline fake)."""
    from ai_avatar.llm.client import LLMClient

    return LLMClient(model=cfg.llm.models[0])
