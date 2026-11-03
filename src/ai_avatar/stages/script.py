"""Script stage: turn researched facts into a short narration with the LLM."""

from ai_avatar.config import Config
from ai_avatar.llm import build_llm

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def generate_script(topic: str, facts: list[str], cfg: Config, llm_client: object | None = None) -> str:
    """Ask the LLM for a ~15-20 second narration about ``topic`` built from ``facts``.

    Errors from the LLM call propagate so the caller can see and fix them.
    """
    prompt = (
        f"You are a short-form narration writer. Given these verified facts about {topic}:\n"
        + "\n".join(f"- {f}" for f in facts)
        + "\n\nWrite a single-paragraph narration of ~15-20 seconds. Keep it factual, concise, and engaging."
    )

    client = llm_client or build_llm(cfg)
    result = client(prompt)

    if isinstance(result, str) and result.strip():
        return result.strip()

    # If the client returned a non-string or empty response, raise to expose the issue
    raise RuntimeError(f"LLM returned empty or non-text response: {result!r}")
