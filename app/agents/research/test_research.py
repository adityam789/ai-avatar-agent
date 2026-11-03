"""Smoke test for ResearchAgent (moves to tests/ in Task 09).

Needs REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET (see .env.example) and network
access; skipped when the credentials are unset.
"""
from __future__ import annotations

import os

import pytest

from .research_agent import ResearchAgent
from ..llm_client import LLMClient


def test_research_agent():
    # Credentials come from the environment (see .env.example); skip when absent.
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    if not (client_id and client_secret):
        pytest.skip("REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set")
    reddit_creds = {
        "client_id": client_id,
        "client_secret": client_secret,
        "user_agent": os.getenv("REDDIT_USER_AGENT", "research-test/0.1"),
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

