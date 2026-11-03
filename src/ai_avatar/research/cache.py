"""Simple cache implementation used by the research agent.

This is intentionally tiny and in-memory. Swap out for Redis or disk as needed.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class ResearchCache:
    """Thread-unsafe in-memory cache.

    Methods:
        find(topic) -> value | None
        store(topic, value)
        clear()
    """

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}

    def find(self, topic: str) -> Optional[Any]:
        return self._store.get(topic)

    def store(self, topic: str, facts: Any, sources: Any) -> None:
        self._store[topic] = {"topic": topic, "facts": facts, "sources": sources, "freshness": "cached"}

    def clear(self) -> None:
        self._store.clear()


