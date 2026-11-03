"""Script stage: turn researched facts into a short narration with the LLM."""

import logging
import math
import re
from collections.abc import Callable
from importlib import resources

from ai_avatar.config import Config
from ai_avatar.errors import LLMError
from ai_avatar.llm import build_llm

log = logging.getLogger(__name__)

WORDS_PER_SECOND = 2.5
TOLERANCE = 0.25  # accepted deviation from the word target

# Emoji, pictographs, dingbats, variation selectors / joiners.
_EMOJI = re.compile("[\U0001f000-\U0001faff←-⇿⌀-⏿☀-➿⬀-⯿️‍]")
_LEADING_LABEL = re.compile(r"^\s*(?:here(?:'s| is)[^\n:]*|narration|script)\s*:\s*", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def generate_script(
    topic: str, facts: list[str], cfg: Config, llm_client: Callable[[str], str] | None = None
) -> str:
    """Write a narration of about ``cfg.script.target_seconds`` seconds about ``topic`` from ``facts``.

    The reply is cleaned for TTS. If its length is outside the word budget (+-25%), the LLM is asked once
    more with a corrective instruction; a reply that is still too long is trimmed at a sentence boundary.
    LLM errors propagate as :class:`~ai_avatar.errors.LLMError`.
    """
    llm = llm_client or build_llm(cfg)
    target = round(cfg.script.target_seconds * WORDS_PER_SECOND)
    low, high = math.ceil(target * (1 - TOLERANCE)), math.floor(target * (1 + TOLERANCE))

    prompt = _build_prompt(topic, facts, cfg, target)
    script = sanitize_for_tts(llm(prompt))
    words = len(script.split())
    if not low <= words <= high:
        log.info("Script has %d words, budget is %d-%d; asking for a rewrite", words, low, high)
        retry = sanitize_for_tts(llm(prompt + _corrective_note(words, target, low, high)))
        script = retry or script
    if not script:
        raise LLMError("The LLM returned no usable narration text.")

    words = len(script.split())
    if words > high:
        script = trim_to_words(script, high)
    elif words < low:
        log.warning("Script has only %d words (budget %d-%d); keeping it", words, low, high)
    return script


def _build_prompt(topic: str, facts: list[str], cfg: Config, target_words: int) -> str:
    template = resources.files("ai_avatar").joinpath("prompts", "script.md").read_text(encoding="utf-8")
    fact_lines = "\n".join(f"- {' '.join(fact.split())}" for fact in facts) or "(none provided)"
    return template.format(
        topic=topic,
        tone=cfg.script.tone,
        target_words=target_words,
        target_seconds=cfg.script.target_seconds,
        facts=fact_lines,
    )


def _corrective_note(words: int, target: int, low: int, high: int) -> str:
    direction = "too long" if words > high else "too short"
    return (
        f"\n\nYour previous draft was {words} words, which is {direction}. Rewrite it with about {target} words "
        f"(between {low} and {high}). Output only the narration."
    )


def sanitize_for_tts(text: str) -> str:
    """Strip markdown, emoji, bracketed/parenthesised stage directions and quotes; collapse whitespace."""
    text = _LEADING_LABEL.sub("", text.strip())
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # [label](url) -> label
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text)  # (pauses), [music fades]
    text = re.sub(r"^\s{0,3}(?:#{1,6}|[-*+>]|\d+\.)\s+", "", text, flags=re.MULTILINE)  # headings, bullets, quotes
    text = re.sub(r"[*_`~]+|(?<!\w)#+", "", text)  # emphasis, code, strikethrough, hashtags
    text = _EMOJI.sub("", text)
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"[\"“”«»]", "", text)
    text = re.sub(r"(?<!\w)'|'(?!\w)", "", text)  # quote marks, but keep apostrophes in "don't"
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)  # gaps left by removed asides
    return " ".join(text.split())


def trim_to_words(text: str, max_words: int) -> str:
    """Keep whole sentences while they fit in ``max_words``; if even the first does not, cut it at the limit."""
    kept: list[str] = []
    count = 0
    for sentence in _SENTENCE_END.split(text):
        size = len(sentence.split())
        if count + size > max_words:
            break
        kept.append(sentence)
        count += size
    if kept:
        return " ".join(kept)
    return " ".join(text.split()[:max_words]).rstrip(",;:") + "."
