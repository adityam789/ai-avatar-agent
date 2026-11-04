"""RSS collector: recent entries from tech-news feeds that actually mention the topic."""

from __future__ import annotations

import html
import logging
import re

import feedparser
import requests

from ai_avatar.redact import scrub
from ai_avatar.research.collectors.base import SourceCollector
from ai_avatar.research.schemas import RawSnippet

log = logging.getLogger(__name__)

RSS_FEEDS = [
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://techcrunch.com/feed/",
    "https://news.ycombinator.com/rss",
]
ENTRIES_PER_FEED = 5  # most snippets taken from one feed (newest matching entries)


def _words(text: str) -> set[str]:
    """Lower-case word set with a trailing plural 's' removed ("computers" matches "computer")."""
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"\w+", text.lower())}


# Question words and fillers that say nothing about the subject ("what is X", "can X do Y"); folded like _words().
_STOPWORDS = _words(
    "a about and are can do does for how in is of on the to was what when where which who why will with"
)


def matches_topic(topic: str, text: str) -> bool:
    """True if every significant word of ``topic`` occurs in ``text`` as a whole word.

    "AI" does not match "said" and "rust" does not match "trust"; stopwords like "how" are ignored.
    """
    words = _words(topic)
    needed = words - _STOPWORDS or words
    return bool(needed) and needed <= _words(text)


def _plain(markup: str) -> str:
    """Feed summaries are often HTML; drop tags and entities."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


class RSSCollector(SourceCollector):
    name = "rss"

    def __init__(self, feeds: list[str] | None = None, timeout: float = 10.0) -> None:
        self.feeds = feeds if feeds is not None else RSS_FEEDS
        self.timeout = timeout

    def collect(self, topic: str) -> list[RawSnippet]:
        snippets: list[RawSnippet] = []
        for feed_url in self.feeds:
            try:
                # feedparser has no timeout of its own, so download the feed ourselves.
                resp = requests.get(feed_url, timeout=self.timeout)
                resp.raise_for_status()
            except requests.RequestException as exc:
                log.warning("rss feed %s skipped: %s", feed_url, scrub(exc))
                continue
            from_feed = 0
            for entry in feedparser.parse(resp.content).entries:
                title = entry.get("title", "") or ""
                summary = _plain(entry.get("summary", "") or "")
                content = " ".join(_plain(c.get("value", "")) for c in entry.get("content", []) or [])
                if not matches_topic(topic, f"{title} {summary} {content}"):
                    continue
                snippets.append(
                    RawSnippet(
                        self.name, title, summary[:1000], entry.get("link", ""), {"published": entry.get("published")}
                    )
                )
                from_feed += 1
                if from_feed == ENTRIES_PER_FEED:
                    break
        return snippets
