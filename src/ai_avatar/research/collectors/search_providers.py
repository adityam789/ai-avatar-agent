"""Web-search backends behind one interface: ``SearchProvider.search(query, n)``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

from ai_avatar.errors import ResearchError
from ai_avatar.redact import scrub
from ai_avatar.research.collectors.fixture import load_fixture


@dataclass
class SearchResult:
    title: str
    text: str
    url: str


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, n: int) -> list[SearchResult]:
        """Up to ``n`` results; raise ``ResearchError`` (or any exception) if the backend is unusable."""
        ...


class DuckDuckGoProvider:
    """Default provider: DuckDuckGo text search via the ``ddgs`` package (no API key).

    Needs the ``search`` extra (``pip install 'ai-avatar-agent[search]'``).
    """

    name = "duckduckgo"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def search(self, query: str, n: int) -> list[SearchResult]:
        try:
            from ddgs import DDGS
        except ImportError:
            raise ResearchError("the 'ddgs' package is not installed: pip install 'ai-avatar-agent[search]'") from None
        hits = DDGS(timeout=int(self.timeout)).text(query, max_results=n)
        return [SearchResult(h.get("title", ""), h.get("body", ""), h.get("href", "")) for h in hits if h.get("title")]


class GoogleCSEProvider:
    """Google Custom Search JSON API. Deprecated: closed to new customers, discontinued 2027-01-01.

    Needs ``GOOGLE_API_KEY`` and ``GOOGLE_CSE_ID``. The key travels in the query string, so request
    errors are re-raised without the original exception (whose message contains the full URL).
    """

    name = "google_cse"
    URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str, cse_id: str, timeout: float = 10.0) -> None:
        self.api_key = api_key
        self.cse_id = cse_id
        self.timeout = timeout

    @classmethod
    def from_env(cls, timeout: float = 10.0) -> GoogleCSEProvider | None:
        """A provider if ``GOOGLE_API_KEY`` and ``GOOGLE_CSE_ID`` are both set, else None."""
        key, cse_id = os.getenv("GOOGLE_API_KEY"), os.getenv("GOOGLE_CSE_ID")
        return cls(key, cse_id, timeout) if key and cse_id else None

    def search(self, query: str, n: int) -> list[SearchResult]:
        params = {"key": self.api_key, "cx": self.cse_id, "q": query, "num": min(n, 10)}
        try:
            resp = requests.get(self.URL, params=params, timeout=self.timeout)
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise ResearchError(f"Google CSE request failed: {scrub(exc)}") from None
        if resp.status_code != 200:
            reason = data.get("error", {}).get("message", "") if isinstance(data, dict) else ""
            raise ResearchError(f"Google CSE returned HTTP {resp.status_code}: {scrub(reason)}")
        return [
            SearchResult(item["title"], item.get("snippet", ""), item.get("link", ""))
            for item in data.get("items", [])
            if item.get("title")
        ]


class StaticProvider:
    """Canned results from a JSON fixture file; for tests and offline demos."""

    name = "static"

    def __init__(self, path: Path) -> None:
        self.path = path

    def search(self, query: str, n: int) -> list[SearchResult]:
        return [
            SearchResult(item["title"], item.get("text", ""), item.get("url", ""))
            for item in load_fixture(self.path)[:n]
        ]
