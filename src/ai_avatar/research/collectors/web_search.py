"""Web-search collector: turns the results of any ``SearchProvider`` into snippets."""

from __future__ import annotations

from ai_avatar.research.collectors.base import SourceCollector
from ai_avatar.research.collectors.search_providers import SearchProvider
from ai_avatar.research.schemas import RawSnippet


class WebSearchCollector(SourceCollector):
    name = "web_search"

    def __init__(self, provider: SearchProvider, num_results: int = 5) -> None:
        self.provider = provider
        self.num_results = num_results

    def collect(self, topic: str) -> list[RawSnippet]:
        results = self.provider.search(topic, self.num_results)
        return [RawSnippet(self.name, r.title, r.text, r.url, {"provider": self.provider.name}) for r in results]
