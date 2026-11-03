"""Offline collector: serves canned snippets from a JSON fixture file."""

from __future__ import annotations

import json
from pathlib import Path

from ai_avatar.research.collectors.base import SourceCollector
from ai_avatar.research.schemas import RawSnippet


def load_fixture(path: Path) -> list[dict]:
    """Read a fixture file: a JSON list of ``{"title", "text", "url"}`` objects."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"fixture {path} must contain a JSON list of snippet objects")
    return data


class FixtureCollector(SourceCollector):
    """Stands in for a real collector in offline mode; ignores the topic and needs no network or keys."""

    def __init__(self, name: str, path: Path) -> None:
        self.name = name
        self.path = path

    def collect(self, topic: str) -> list[RawSnippet]:
        return [
            RawSnippet(self.name, item["title"], item.get("text", ""), item.get("url", ""))
            for item in load_fixture(self.path)
        ]
