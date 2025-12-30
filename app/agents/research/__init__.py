"""Research agents package.

This package exposes the ResearchAgent and commonly used helpers.
"""

from .research_agent import ResearchAgent
from .aggregator import LLMAggregator
from .cache import ResearchCache
from typing import Optional

from ..llm_client import LLMClient


def run_research(topic: str, llm_client: Optional[object] = None, reddit_creds: Optional[dict] = None):
	"""Programmatic entrypoint: run the research pipeline and return a ResearchBundle.

	If `llm_client` is not supplied, an `LLMClient()` will be instantiated using
	environment configuration (OPEN_ROUTER_API_KEY). `reddit_creds` is passed
	through to the ResearchAgent constructor.
	"""
	if llm_client is None:
		llm_client = LLMClient()

	if reddit_creds is None:
		reddit_creds = {}

	agent = ResearchAgent(llm_client, reddit_creds)
	return agent.run(topic)

__all__ = ["ResearchAgent", "LLMAggregator", "ResearchCache"]
