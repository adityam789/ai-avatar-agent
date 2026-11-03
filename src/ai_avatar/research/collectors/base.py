"""Collector contract and the failure-isolating wrapper used by the agent."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ai_avatar.redact import scrub
from ai_avatar.research.schemas import RawSnippet

log = logging.getLogger(__name__)


class SourceCollector(ABC):
    """A research source. ``collect`` returns snippets about a topic and may raise on failure."""

    name: str

    @abstractmethod
    def collect(self, topic: str) -> list[RawSnippet]: ...


def safe_collect(collector: SourceCollector, topic: str) -> list[RawSnippet]:
    """Run ``collector``; log a warning and return ``[]`` instead of raising.

    One dead service (network error, revoked key, missing optional package) must not
    stop research, so every exception is caught here. Messages go through ``scrub``
    because HTTP errors embed URLs that may carry API keys.
    """
    try:
        return collector.collect(topic)
    except Exception as exc:  # noqa: BLE001 - isolating arbitrary collector failures is the point
        log.warning("%s collector failed (%s): %s", collector.name, type(exc).__name__, scrub(exc))
        return []
