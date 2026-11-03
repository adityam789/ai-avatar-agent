"""Pull a JSON object out of an LLM reply that may be wrapped in prose or code fences."""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?", re.IGNORECASE)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _first_object(text: str) -> dict | None:
    """The first ``{...}`` in ``text`` that decodes as a JSON object; prose around it is ignored."""
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, _ = decoder.raw_decode(text, start)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
        start = text.find("{", start + 1)
    return None


def extract_json_object(text: str) -> dict:
    """Parse the JSON object in ``text``, tolerating code fences, surrounding prose and trailing commas.

    Raises ``ValueError`` if no JSON object can be found.
    """
    text = _FENCE.sub("", text).strip()
    # Try the text as-is first: removing "trailing commas" could change commas inside strings.
    found = _first_object(text) or _first_object(_TRAILING_COMMA.sub(r"\1", text))
    if found is None:
        raise ValueError("no JSON object found in text")
    return found
