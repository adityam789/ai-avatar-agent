"""Small test runner for the ResearchAgent.

This file can be executed directly to smoke-test the ResearchAgent with the
stub collectors that live in `app.agents.research.collectors`.
"""
from __future__ import annotations

from .research_agent import ResearchAgent
from ..llm_client import LLMClient


def test_research_agent():
    reddit_creds = {
        "client_id": "mkCkbZxe4vlE6VCaylxQPQ",
        "client_secret": "U8SQ3W7qqvZjRzQob6GgXOWYCCz0tQ",
        "user_agent": "research-test/0.1",
    }

    agent = ResearchAgent(LLMClient(), reddit_creds)

    topic = "openai"
    print(f"Running ResearchAgent for topic: '{topic}' (first run - should be fresh)")
    bundle1 = agent.run(topic)
    print("bundle1:", bundle1)
    print("Facts:")
    for f in bundle1.facts:
        print(" -", f)

    print("\nRunning ResearchAgent a second time with same topic (should hit cache)")
    bundle2 = agent.run(topic)
    print("bundle2:", bundle2)

    return bundle1, bundle2


if __name__ == "__main__":
    test_research_agent()
