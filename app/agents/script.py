from typing import Optional
import os

from .research import run_research
from .llm_client import LLMClient

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def generate_script(topic: str, llm_client: Optional[object] = None) -> str:
    """Generate a short narration script for `topic` by running the research
    pipeline and asking an LLM to synthesize a 12–15s narration from the facts.

    Errors from the research pipeline or the LLM call are allowed to propagate
    so the caller can see and fix them.
    """
    # Gather reddit credentials from environment (loaded from .env by LLMClient module)
    reddit_client_id = os.getenv("REDDIT_CLIENT_ID")
    reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    reddit_user_agent = os.getenv("REDDIT_USER_AGENT")

    reddit_creds = None
    if reddit_client_id and reddit_client_secret and reddit_user_agent:
        reddit_creds = {
            "client_id": reddit_client_id,
            "client_secret": reddit_client_secret,
            "user_agent": reddit_user_agent,
        }

    bundle = run_research(topic, reddit_creds=reddit_creds)
    facts = bundle.facts if hasattr(bundle, "facts") else []

    prompt = (
        f"You are a short-form narration writer. Given these verified facts about {topic}:\n"
        + "\n".join([f"- {f}" for f in facts])
        + "\n\nWrite a single-paragraph narration of ~15-20 seconds. Keep it factual, concise, and engaging."
    )

    client = llm_client or LLMClient()
    result = client(prompt)

    if isinstance(result, str) and result.strip():
        return result.strip()

    # If the client returned a non-string or empty response, raise to expose the issue
    raise RuntimeError(f"LLM returned empty or non-text response: {result!r}")
