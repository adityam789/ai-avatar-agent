"""Reddit collector using praw (optional ``reddit`` extra; the API now requires approval)."""

from __future__ import annotations

import os

from ai_avatar.research.collectors.base import SourceCollector
from ai_avatar.research.schemas import RawSnippet

SUBREDDITS = ["explainlikeimfive", "science", "technology", "aviation"]
MIN_SCORE = 50
MIN_COMMENTS = 10


def reddit_creds_from_env() -> dict[str, str] | None:
    """Reddit credentials from the environment, or None unless all three are set."""
    creds = {
        "client_id": os.getenv("REDDIT_CLIENT_ID"),
        "client_secret": os.getenv("REDDIT_CLIENT_SECRET"),
        "user_agent": os.getenv("REDDIT_USER_AGENT"),
    }
    return creds if all(creds.values()) else None


class RedditCollector(SourceCollector):
    """Popular posts about the topic. Raises ``ImportError`` at construction if praw is missing."""

    name = "reddit"

    def __init__(self, client_id: str, client_secret: str, user_agent: str, timeout: float = 10.0) -> None:
        import praw

        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
            requestor_kwargs={"timeout": timeout},
        )

    def collect(self, topic: str) -> list[RawSnippet]:
        snippets: list[RawSnippet] = []
        for sub in SUBREDDITS:
            for post in self.reddit.subreddit(sub).search(topic, limit=3):
                score, comments = getattr(post, "score", 0), getattr(post, "num_comments", 0)
                if score < MIN_SCORE or comments < MIN_COMMENTS:
                    continue
                snippets.append(
                    RawSnippet(
                        self.name,
                        post.title,
                        (getattr(post, "selftext", "") or "")[:1000],
                        getattr(post, "url", ""),
                        {"score": score + comments * 2, "subreddit": sub},
                    )
                )
        return snippets
