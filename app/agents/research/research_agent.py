"""Research agent orchestration.

This module provides a minimal ResearchAgent class which coordinates collectors,
aggregator and cache to fetch and aggregate external data.
"""
from .schemas import ResearchBundle
from .collectors.reddit import RedditCollector
from .collectors.google_cse import GoogleCSECollector
from .collectors.rss import RSSCollector
from .aggregator import LLMAggregator
from .cache import ResearchCache

class ResearchAgent:

    def __init__(self, llm_client, reddit_creds):
        self.cache = ResearchCache()
        self.collectors = [
            RedditCollector(**reddit_creds),
            GoogleCSECollector(),
            RSSCollector(),
        ]
        self.aggregator = LLMAggregator(llm_client)

    def run(self, topic: str) -> ResearchBundle:
        cached = self.cache.find(topic)
        if cached:
            return ResearchBundle(
                topic=cached["topic"],
                facts=cached["facts"],
                freshness=cached["freshness"],
                sources=cached["sources"]
            )

        snippets = []
        sources = set()

        for collector in self.collectors:
            collected = collector.collect(topic)
            snippets.extend(collected)
            for s in collected:
                sources.add(s.source)

        facts = self.aggregator.aggregate(topic, snippets)

        bundle = ResearchBundle(
            topic=topic,
            facts=facts,
            freshness="fresh",
            sources=list(sources)
        )

        self.cache.store(topic, facts, list(sources))
        return bundle
