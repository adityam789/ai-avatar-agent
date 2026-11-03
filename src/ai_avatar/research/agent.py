"""Research agent: run the collectors, de-duplicate their snippets, distil facts, cache the result."""

from __future__ import annotations

import logging

from ai_avatar.errors import ResearchError
from ai_avatar.research.aggregator import LLMAggregator, dedupe_snippets
from ai_avatar.research.cache import ResearchCache
from ai_avatar.research.collectors.base import SourceCollector, safe_collect
from ai_avatar.research.schemas import ResearchBundle

log = logging.getLogger(__name__)


class ResearchAgent:
    def __init__(
        self, collectors: list[SourceCollector], aggregator: LLMAggregator, cache: ResearchCache | None = None
    ) -> None:
        self.collectors = collectors
        self.aggregator = aggregator
        self.cache = cache

    def run(self, topic: str) -> ResearchBundle:
        """Facts about ``topic``. Raises ``ResearchError`` if no collector produced any snippet."""
        if self.cache and (cached := self.cache.find(topic)):
            log.info("research cache hit for %r", topic)
            return cached

        snippets = []
        for collector in self.collectors:
            found = safe_collect(collector, topic)
            log.info("%s collector: %d snippets", collector.name, len(found))
            snippets.extend(found)
        snippets = dedupe_snippets(snippets)
        if not snippets:
            tried = ", ".join(c.name for c in self.collectors) or "none enabled"
            raise ResearchError(
                f"no snippets collected for {topic!r} (collectors tried: {tried}). Check your network connection "
                "and the warnings above, enable a source in research.collectors, or run with --offline."
            )

        bundle = ResearchBundle(
            topic=topic,
            facts=self.aggregator.aggregate(topic, snippets),
            freshness="fresh",
            sources=list(dict.fromkeys(s.source for s in snippets)),
            source_links=[{"source": s.source, "title": s.title, "url": s.url} for s in snippets],
        )
        if self.cache:
            self.cache.store(bundle)
        return bundle
