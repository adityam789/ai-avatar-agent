"""Script stage: turn researched facts into a short narration with the LLM."""

import logging
import math
import re
from collections.abc import Callable
from importlib import resources

from ai_avatar.config import Config
from ai_avatar.errors import LLMError
from ai_avatar.llm import build_llm
from ai_avatar.redact import scrub

log = logging.getLogger(__name__)

WORDS_PER_SECOND = 2.5
TOLERANCE = 0.25  # accepted deviation from the word target

# Emoji, pictographs, dingbats, variation selectors / joiners / keycap combiner.
_EMOJI = re.compile("[\U0001f000-\U0001faff\u2190-\u21ff\u2300-\u23ff\u2600-\u27bf\u2b00-\u2bff\ufe0f\u200d\u20e3]")
# A label line such as "Here is your script:" (must end the first line) or "Narration: " before the text.
_LEADING_LABEL = re.compile(
    r"^\s*(?:here(?:['\u2019]s| is)\b[^\n.!?:]{0,60}:[ \t]*\n|(?:narration|script)\s*:\s*)", re.IGNORECASE
)
_STAGE_WORDS = (
    "pause|beat|music|sfx|sound effects?|applause|silence|laughs?|laughing|laughter|chuckles?|sighs?|gasps?|coughs?"
    "|whispers?|whispering|smiles?|smiling|cut to|fade|clears throat|dramatic|long pause|short pause|excitedly"
    "|softly|quietly|slowly|sarcastically"
)
_STAGE_DIRECTION = re.compile(rf"\(\s*(?:\*|(?:{_STAGE_WORDS})\b)[^)]*\)|\[[^\]]*\]", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def generate_script(
    topic: str, facts: list[str], cfg: Config, llm_client: Callable[[str], str] | None = None
) -> str:
    """Write a narration of about ``cfg.script.target_seconds`` seconds about ``topic`` from ``facts``.

    The reply is cleaned for TTS. If its length is outside the word budget (+-25%), the LLM is asked once
    more with a corrective instruction and the draft closer to the target (after trimming) is kept; a draft
    that is too long is trimmed at a sentence boundary. LLM errors propagate as
    :class:`~ai_avatar.errors.LLMError`, except that a failed rewrite request keeps a non-empty first draft.
    """
    llm = llm_client or build_llm(cfg)
    target = int(cfg.script.target_seconds * WORDS_PER_SECOND + 0.5)  # half-up, unlike round()
    low, high = math.ceil(target * (1 - TOLERANCE)), math.floor(target * (1 + TOLERANCE))

    prompt = _build_prompt(topic, facts, cfg, target)
    first = sanitize_for_tts(llm(prompt))
    words = len(first.split())
    drafts = [first]
    if not low <= words <= high:
        log.info("Script has %d words, budget is %d-%d; asking for a rewrite", words, low, high)
        try:
            drafts.append(sanitize_for_tts(llm(prompt + _corrective_note(words, target, low, high))))
        except LLMError as exc:
            if not first:
                raise
            log.warning("Rewrite request failed (%s); keeping the first draft", scrub(exc))
    # Each draft as it would be delivered, so a long draft is judged by its trimmed length. Ties keep the first.
    finals = [_fit_to_budget(d, low, high) for d in drafts if d]
    if not finals:
        raise LLMError("The LLM returned no usable narration text.")
    script = min(finals, key=lambda d: abs(len(d.split()) - target))
    if len(script.split()) < low:
        log.warning("Script has only %d words (budget %d-%d); keeping it", len(script.split()), low, high)
    return script


def _fit_to_budget(draft: str, low: int, high: int) -> str:
    """Trim an over-long draft; shorter drafts are returned as they are (they cannot be padded honestly)."""
    return trim_to_words(draft, high, low) if len(draft.split()) > high else draft


def _build_prompt(topic: str, facts: list[str], cfg: Config, target_words: int) -> str:
    template = resources.files("ai_avatar").joinpath("prompts", "script.md").read_text(encoding="utf-8")
    fact_lines = "\n".join(f"- {' '.join(fact.split())}" for fact in facts)
    return template.format(
        topic=" ".join(topic.split()),
        tone=cfg.script.tone,
        target_words=target_words,
        target_seconds=cfg.script.target_seconds,
        facts=fact_lines or "None provided. Keep the narration general and avoid specific claims.",
    )


def _corrective_note(words: int, target: int, low: int, high: int) -> str:
    direction = "too long" if words > high else "too short"
    return (
        f"\n\nYour previous draft was {words} words, which is {direction}. Rewrite it with about {target} words "
        f"(between {low} and {high}). Output only the narration."
    )


def sanitize_for_tts(text: str) -> str:
    """Make ``text`` speakable: drop markdown, emoji, stage directions and quotes, keep ordinary asides.

    Bracketed text and parentheticals that look like stage directions ("(pause)", "(music fades)") are removed;
    other parentheticals keep their words but lose the parentheses. ``#1`` becomes "number 1", ``~50`` (also
    ``~$5``, ``~-3``) "about 50" and ``5 * 3`` "5 times 3".
    """
    text = _LEADING_LABEL.sub("", text.strip())
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # [label](url) -> label
    text = _STAGE_DIRECTION.sub(" ", text)
    text = re.sub(r"^\s{0,3}(?:#{1,6}|[-*+>]|\d+\.)\s+", "", text, flags=re.MULTILINE)  # headings, bullets, quotes
    text = re.sub(r"(?<=\d)\s*\*\s*(?=\d)", " times ", text)  # 5 * 3, 2*3*4
    text = re.sub(r"(?<!\w)(\*\*|\*)(?=\S)(.+?)(?<=\S)\1(?!\w)", r"\2", text)  # *emphasis*, **strong**
    text = re.sub(r"(__|~~|`)(?=\S)(.+?)(?<=\S)\1", r"\2", text)  # paired code, strike, underscore strong
    text = re.sub(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", r"\1", text)  # _italic_ but not snake_case
    text = re.sub(r"[*`]+|[()\[\]]", " ", text)  # leftovers: stray markers, parentheses of ordinary asides
    text = re.sub(r"#(?=\d)", "number ", text)
    text = re.sub(r"(?<!\w)#+|~(?![$\u00a3\u20ac]?-?\d)", "", text)  # hashtags (not C#), stray tildes
    text = text.replace("~", "about ")
    text = _EMOJI.sub("", text)
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = re.sub(r"[\"\u201c\u201d\u00ab\u00bb]", "", text)
    text = re.sub(r"(?<!\w)'|'(?!\w)", "", text)  # quote marks, but keep apostrophes in "don't"
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)  # gaps left by removed asides
    return " ".join(text.split())


def trim_to_words(text: str, max_words: int, min_words: int = 0) -> str:
    """Keep whole sentences while they fit in ``max_words``.

    If that leaves fewer than ``min_words`` words (a tiny first sentence such as "Wow." or "Dr."), cut at
    ``max_words`` instead, on a word boundary.
    """
    kept: list[str] = []
    count = 0
    for sentence in _SENTENCE_END.split(text):
        size = len(sentence.split())
        if count + size > max_words:
            break
        kept.append(sentence)
        count += size
    if kept and count >= min_words:
        return " ".join(kept)
    cut = " ".join(text.split()[:max_words]).rstrip(",;:")
    return cut if cut.endswith((".", "!", "?")) else cut + "."
