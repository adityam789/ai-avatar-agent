"""Collectors package for research agent.

Expose collector implementations and the base collector type.
"""
from ai_avatar.research.collectors.base import SourceCollector
from ai_avatar.research.collectors.reddit import RedditCollector
from ai_avatar.research.collectors.google_cse import GoogleCSECollector
from ai_avatar.research.collectors.rss import RSSCollector

__all__ = ["SourceCollector", "RedditCollector", "GoogleCSECollector", "RSSCollector"]
