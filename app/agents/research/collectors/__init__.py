"""Collectors package for research agent.

Expose collector implementations and the base collector type.
"""
from .base import SourceCollector
from .reddit import RedditCollector
from .google_cse import GoogleCSECollector
from .rss import RSSCollector

__all__ = ["SourceCollector", "RedditCollector", "GoogleCSECollector", "RSSCollector"]
