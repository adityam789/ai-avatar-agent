"""Collector registry: builds the collectors enabled in ``cfg.research.collectors``."""

from __future__ import annotations

import logging

from ai_avatar.config import Config
from ai_avatar.research.collectors.base import SourceCollector, safe_collect
from ai_avatar.research.collectors.fixture import FixtureCollector
from ai_avatar.research.collectors.reddit import RedditCollector, reddit_creds_from_env
from ai_avatar.research.collectors.rss import RSSCollector
from ai_avatar.research.collectors.search_providers import (
    DuckDuckGoProvider,
    GoogleCSEProvider,
    SearchProvider,
    StaticProvider,
)
from ai_avatar.research.collectors.web_search import WebSearchCollector

log = logging.getLogger(__name__)


def _search_provider(cfg: Config) -> SearchProvider | None:
    """The configured web-search provider, or None (with a log line) if it cannot be used."""
    timeout = cfg.research.timeout_seconds
    match cfg.research.search_provider:
        case "duckduckgo":
            return DuckDuckGoProvider(timeout)
        case "google_cse":
            provider = GoogleCSEProvider.from_env(timeout)
            if provider is None:
                log.warning("web_search skipped: google_cse needs GOOGLE_API_KEY and GOOGLE_CSE_ID (deprecated API)")
            return provider
        case _:
            return StaticProvider(cfg.resolve(cfg.research.fixtures_dir) / "web_search.json")


def _reddit(cfg: Config) -> RedditCollector | None:
    creds = reddit_creds_from_env()
    if creds is None:
        log.info("reddit collector skipped: REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET / REDDIT_USER_AGENT not all set")
        return None
    try:
        return RedditCollector(**creds, timeout=cfg.research.timeout_seconds)
    except ImportError:
        log.info("reddit collector skipped: praw is not installed (pip install 'ai-avatar-agent[reddit]')")
        return None


def build_collectors(cfg: Config) -> list[SourceCollector]:
    """Collectors for ``cfg.research.collectors``; sources that cannot be set up are skipped, not fatal.

    In offline mode every enabled collector is replaced by a fixture reader
    (``<fixtures_dir>/<collector name>.json``), so no network or keys are involved.
    """
    names = cfg.research.collectors
    if cfg.offline:
        fixtures = cfg.resolve(cfg.research.fixtures_dir)
        return [FixtureCollector(name, fixtures / f"{name}.json") for name in names]

    collectors: list[SourceCollector | None] = []
    for name in names:
        if name == "rss":
            collectors.append(RSSCollector(timeout=cfg.research.timeout_seconds))
        elif name == "web_search":
            provider = _search_provider(cfg)
            collectors.append(WebSearchCollector(provider) if provider else None)
        elif name == "reddit":
            collectors.append(_reddit(cfg))
    return [c for c in collectors if c is not None]


__all__ = ["SourceCollector", "safe_collect", "build_collectors"]
