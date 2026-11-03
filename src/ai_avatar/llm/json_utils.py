"""Pull a JSON object out of an LLM reply that may be wrapped in prose or code fences."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _objects(text: str) -> Iterator[dict]:
    """JSON objects found in ``text``, left to right, outermost first.

    Code fences and prose around an object need no special handling: decoding starts at each ``{``.
    At every ``{`` the text is tried as-is first (removing "trailing commas" could change commas inside
    strings); only if that fails is the trailing-comma repair applied, so a damaged outer object is still
    preferred over the valid objects nested inside it.
    """
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        tail = text[start:]
        end = start + 1
        for repaired, candidate in ((False, tail), (True, _TRAILING_COMMA.sub(r"\1", tail))):
            try:
                value, length = decoder.raw_decode(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value
                if not repaired:
                    end = start + length  # skip the objects nested inside this one
                break
        start = text.find("{", end)


def extract_json_object(text: str, want_key: str | None = None) -> dict:
    """Parse the JSON object in ``text``, tolerating code fences, surrounding prose and trailing commas.

    If ``want_key`` is given, the first object containing that key wins (the reply may hold other objects,
    such as a note before the answer); otherwise the first object found is returned.
    Raises ``ValueError`` if no JSON object can be found.
    """
    first = None
    for obj in _objects(text):
        if want_key is None or want_key in obj:
            return obj
        first = first if first is not None else obj
    if first is None:
        raise ValueError("no JSON object found in text")
    return first
