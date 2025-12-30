"""RSS collector stub."""
import feedparser
from typing import List
from ..schemas import RawSnippet
from .base import SourceCollector

RSS_FEEDS = [
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://techcrunch.com/feed/",
    "https://news.ycombinator.com/rss",
]


class RSSCollector(SourceCollector):

    def collect(self, topic: str) -> List[RawSnippet]:
        snippets = []

        for feed_url in RSS_FEEDS:
            feed = feedparser.parse(feed_url)
            for entry in getattr(feed, "entries", [])[:5]:
                # be defensive: title/summary may be missing
                title = getattr(entry, "title", "") or ""
                summary = getattr(entry, "summary", "") or ""

                # Some feeds put the main content in `content` as a list of dicts
                content_text = ""
                if hasattr(entry, "content") and isinstance(entry.content, list) and len(entry.content) > 0:
                    # feedparser returns content entries as objects with a `value`
                    first = entry.content[0]
                    content_text = getattr(first, "value", "") or ""

                hay = (title + "\n" + summary + "\n" + content_text).lower()
                if topic.lower() not in hay:
                    # skip entries that don't mention the topic in title/summary/content
                    continue

                snippets.append(
                    RawSnippet(
                        source="rss",
                        title=title,
                        text=summary[:1000],
                        metadata={
                            "link": getattr(entry, "link", ""),
                            "published": entry.get("published") if hasattr(entry, "published") else None,
                        },
                    )
                )

        return snippets

