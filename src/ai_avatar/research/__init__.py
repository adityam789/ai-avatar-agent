"""Research package: collect snippets about a topic and distil them into facts."""

from ai_avatar.research.agent import ResearchAgent
from ai_avatar.research.aggregator import LLMAggregator
from ai_avatar.research.cache import ResearchCache
from ai_avatar.config import Config
from ai_avatar.llm import build_llm
import os


def reddit_creds_from_env() -> dict | None:
    """Reddit credentials from the environment, or None unless all three are set."""
    creds = {
        "client_id": os.getenv("REDDIT_CLIENT_ID"),
        "client_secret": os.getenv("REDDIT_CLIENT_SECRET"),
        "user_agent": os.getenv("REDDIT_USER_AGENT"),
    }
    return creds if all(creds.values()) else None


def run_research(topic: str, cfg: Config):
    """Research ``topic`` and return a ResearchBundle (Task 06 reworks the collectors behind this)."""
    agent = ResearchAgent(build_llm(cfg), reddit_creds_from_env() or {})
    return agent.run(topic)


__all__ = ["reddit_creds_from_env", "run_research", "ResearchAgent", "LLMAggregator", "ResearchCache"]
