"""Collector contract and the failure-isolating wrapper used by the agent."""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod

from ai_avatar.redact import scrub
from ai_avatar.research.schemas import RawSnippet

log = logging.getLogger(__name__)


class SourceCollector(ABC):
    """A research source. ``collect`` returns snippets about a topic and may raise on failure."""

    name: str

    @abstractmethod
    def collect(self, topic: str) -> list[RawSnippet]: ...


def collector_name(collector: SourceCollector) -> str:
    """The collector's ``name``, falling back to its class name for subclasses that forgot to set one."""
    return getattr(collector, "name", type(collector).__name__)


def safe_collect(collector: SourceCollector, topic: str, timeout: float | None = None) -> list[RawSnippet]:
    """Run ``collector``; log a warning and return ``[]`` instead of raising.

    One dead service (network error, revoked key, missing optional package) must not
    stop research, so every exception is caught here. Messages go through ``scrub``
    because HTTP errors embed URLs that may carry API keys.

    ``timeout`` is a wall-clock limit in seconds for the whole ``collect`` call (per-request timeouts
    do not bound a collector that makes several requests). A collector that overruns is abandoned:
    it keeps running in a daemon thread, so it can neither block the run nor delay interpreter exit.
    """
    name = collector_name(collector)
    outcome: list[list[RawSnippet]] = []
    errors: list[Exception] = []

    def work() -> None:
        try:
            outcome.append(collector.collect(topic))
        except Exception as exc:  # noqa: BLE001 - isolating arbitrary collector failures is the point
            errors.append(exc)

    worker = threading.Thread(target=work, name=f"collect-{name}", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        log.warning("%s collector timed out after %gs and was skipped", name, timeout)
        return []
    if errors:
        log.warning("%s collector failed (%s): %s", name, type(errors[0]).__name__, scrub(errors[0]))
        return []
    return outcome[0]
