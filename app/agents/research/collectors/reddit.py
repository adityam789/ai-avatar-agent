"""Reddit collector using praw.

This collector expects a configured praw.Reddit instance via client_id,
client_secret and user_agent. It returns RawSnippet dataclasses.
"""
import praw
from typing import List
from ..schemas import RawSnippet
from .base import SourceCollector


class RedditCollector(SourceCollector):

    def __init__(self, client_id, client_secret, user_agent):
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )

        self.subreddits = [
            "explainlikeimfive",
            "science",
            "technology",
            "aviation",
        ]

    def collect(self, topic: str) -> List[RawSnippet]:
        snippets: List[RawSnippet] = []

        for sub in self.subreddits:
            for post in self.reddit.subreddit(sub).search(topic, limit=3):
                if getattr(post, "score", 0) < 50 or getattr(post, "num_comments", 0) < 10:
                    continue

                snippets.append(
                    RawSnippet(
                        source="reddit",
                        title=post.title,
                        text=(getattr(post, "selftext", "") or "")[:1000],
                        metadata={
                            "score": getattr(post, "score", 0) + (getattr(post, "num_comments", 0) * 2),
                            "url": getattr(post, "url", ""),
                            "subreddit": sub,
                        },
                    )
                )

        return snippets

