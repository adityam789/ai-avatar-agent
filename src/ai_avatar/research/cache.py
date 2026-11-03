"""Research result caches with a time-to-live. Both classes share ``find`` / ``store``."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from ai_avatar.research.schemas import ResearchBundle

log = logging.getLogger(__name__)


def _slug(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:60] or "topic"


class ResearchCache:
    """In-memory cache. Entries older than ``ttl_hours`` are never returned.

    ``clock`` returns the current time in seconds; tests inject a fake one.
    """

    def __init__(self, ttl_hours: float = 24.0, clock: Callable[[], float] = time.time) -> None:
        self.ttl_seconds = ttl_hours * 3600
        self.clock = clock
        self._entries: dict[str, tuple[float, ResearchBundle]] = {}

    def find(self, topic: str) -> ResearchBundle | None:
        """The stored bundle (marked ``freshness="cached"``), or None if absent or expired."""
        entry = self._entries.get(topic)
        if entry is None or self.clock() - entry[0] >= self.ttl_seconds:
            return None
        return replace(entry[1], freshness="cached")

    def store(self, bundle: ResearchBundle) -> None:
        self._entries[bundle.topic] = (self.clock(), bundle)


class DiskResearchCache(ResearchCache):
    """JSON files in ``directory``, one per topic slug and UTC date: ``<date>_<slug>.json``.

    Unreadable or mismatching files count as a miss. Old files are left in place; delete the
    directory to clear the cache.
    """

    def __init__(self, directory: Path, ttl_hours: float = 24.0, clock: Callable[[], float] = time.time) -> None:
        super().__init__(ttl_hours, clock)
        self.directory = directory

    def _path(self, topic: str, at: float) -> Path:
        day = datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%d")
        return self.directory / f"{day}_{_slug(topic)}.json"

    def find(self, topic: str) -> ResearchBundle | None:
        now = self.clock()
        path = self._path(topic, now)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            bundle = ResearchBundle(**record["bundle"])
            stored_at = float(record["stored_at"])
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("ignoring unreadable research cache file %s (%s)", path, type(exc).__name__)
            return None
        if bundle.topic != topic or now - stored_at >= self.ttl_seconds:
            return None
        return replace(bundle, freshness="cached")

    def store(self, bundle: ResearchBundle) -> None:
        now = self.clock()
        path = self._path(bundle.topic, now)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"stored_at": now, "bundle": asdict(bundle)}, indent=2), encoding="utf-8")
        except OSError as exc:  # a read-only cache directory must not fail the run
            log.warning("could not write research cache file %s (%s)", path, type(exc).__name__)
