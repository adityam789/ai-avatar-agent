"""Research result caches with a time-to-live. Both classes share ``find`` / ``store``."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
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

    def _is_fresh(self, stored_at: float, now: float) -> bool:
        """Younger than the TTL; an entry from the "future" (clock moved backwards) is not trusted."""
        return 0 <= now - stored_at < self.ttl_seconds

    def find(self, topic: str) -> ResearchBundle | None:
        """The stored bundle (marked ``freshness="cached"``), or None if absent or expired."""
        entry = self._entries.get(topic)
        if entry is None or not self._is_fresh(entry[0], self.clock()):
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
        if bundle.topic != topic or not self._is_fresh(stored_at, now):
            return None
        return replace(bundle, freshness="cached")

    def store(self, bundle: ResearchBundle) -> None:
        now = self.clock()
        path = self._path(bundle.topic, now)
        tmp_name = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write a temp file next to the target, then rename: readers never see a half-written file.
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
            ) as tmp:
                tmp_name = tmp.name
                json.dump({"stored_at": now, "bundle": asdict(bundle)}, tmp, indent=2)
            os.replace(tmp_name, path)
        except BaseException as exc:
            if tmp_name:
                Path(tmp_name).unlink(missing_ok=True)  # never leave a stray temp file behind
            if not isinstance(exc, OSError):
                raise
            # a read-only cache directory must not fail the run
            log.warning("could not write research cache file %s (%s)", path, type(exc).__name__)
