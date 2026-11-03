"""Research package: collect snippets about a topic and distil them into facts."""

from ai_avatar.research.agent import ResearchAgent
from ai_avatar.research.aggregator import LLMAggregator
from ai_avatar.research.cache import ResearchCache
from ai_avatar.llm.client import LLMClient
import os


def reddit_creds_from_env() -> dict | None:
    """Reddit credentials from the environment, or None unless all three are set."""
    creds = {
        "client_id": os.getenv("REDDIT_CLIENT_ID"),
        "client_secret": os.getenv("REDDIT_CLIENT_SECRET"),
        "user_agent": os.getenv("REDDIT_USER_AGENT"),
    }
    return creds if all(creds.values()) else None


def run_research(topic: str, llm_client: object | None = None, reddit_creds: dict | None = None):
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

__all__ = ["reddit_creds_from_env", "run_research", "ResearchAgent", "LLMAggregator", "ResearchCache"]
