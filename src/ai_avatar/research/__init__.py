"""Research stage: collect snippets about a topic and distil them into facts."""

from ai_avatar.config import Config
from ai_avatar.llm import build_llm
from ai_avatar.research.agent import ResearchAgent
from ai_avatar.research.aggregator import LLMAggregator
from ai_avatar.research.cache import DiskResearchCache, ResearchCache
from ai_avatar.research.collectors import build_collectors
from ai_avatar.research.schemas import ResearchBundle


def run_research(topic: str, cfg: Config) -> ResearchBundle:
    """Research ``topic`` with the collectors enabled in ``cfg.research``.

    Results are cached on disk for ``cache_ttl_hours``; offline mode reads fixtures and skips the cache.
    """
    research = cfg.research
    cache = None if cfg.offline else DiskResearchCache(cfg.resolve(research.cache_dir), research.cache_ttl_hours)
    aggregator = LLMAggregator(build_llm(cfg), research.max_snippet_chars)
    return ResearchAgent(build_collectors(cfg), aggregator, cache).run(topic)


__all__ = ["run_research", "ResearchAgent", "LLMAggregator", "ResearchCache", "DiskResearchCache", "ResearchBundle"]
