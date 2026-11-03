"""LLM access. Stages call ``build_llm(cfg)`` and then ``llm(prompt) -> str``."""

import os
from collections.abc import Callable

from ai_avatar.config import Config
from ai_avatar.llm.client import API_KEY_ENV, LLMClient
from ai_avatar.llm.fake import FakeLLM

__all__ = ["FakeLLM", "LLMClient", "build_llm"]


def build_llm(cfg: Config) -> Callable[[str], str]:
    """The offline :class:`FakeLLM`, or an :class:`LLMClient` for ``cfg.llm`` using keys from the environment.

    A missing ``OPEN_ROUTER_API_KEY`` is reported (as ``LLMError``) on the first call, before any request is sent.
    """
    if cfg.offline:
        return FakeLLM()
    return LLMClient(
        cfg.llm.models,
        cfg.llm.base_url,
        os.getenv(API_KEY_ENV, ""),
        max_retries=cfg.llm.max_retries,
        timeout_seconds=cfg.llm.timeout_seconds,
        referer=os.getenv("OPEN_ROUTER_REFERER") or None,
        title=os.getenv("OPEN_ROUTER_TITLE") or None,
    )
