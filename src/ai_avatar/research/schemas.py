"""Data shapes shared by the research package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class RawSnippet:
    """One piece of text found by a collector."""

    source: str  # collector name: "rss", "web_search" or "reddit"
    title: str
    text: str
    url: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class ResearchBundle:
    """Result of the research stage; written to ``research.json`` (the script stage reads ``facts``)."""

    topic: str
    facts: list[str]
    freshness: Literal["cached", "fresh"]
    sources: list[str]  # names of the collectors that contributed snippets
    source_links: list[dict[str, str]] = field(default_factory=list)  # {"source", "title", "url"} per snippet used
