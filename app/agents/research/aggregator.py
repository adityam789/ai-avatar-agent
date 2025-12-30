"""Aggregator for merging results from multiple collectors.

This module provides a simple Aggregator that concatenates item lists and
performs minimal de-duplication by URL.
"""
import json
from typing import List
from .schemas import RawSnippet

class LLMAggregator:

    def __init__(self, llm_client):
        self.llm = llm_client

    def aggregate(self, topic: str, snippets: List[RawSnippet]) -> List[str]:
        prompt = self._prompt(topic, snippets)
        print("Aggregator prompt:", prompt)
        response = self.llm(prompt)

        # The LLM client may return either a JSON string or already-parsed dict.
        # Be defensive: accept both and provide a helpful error when parsing fails.
        data = None
        if isinstance(response, dict):
            data = response
        else:
            # attempt to parse string responses
            try:
                data = json.loads(response)
            except Exception:
                # try to salvage JSON embedded in the response (trim surrounding text)
                if isinstance(response, str):
                    s = response.strip()
                    first = s.find("{")
                    last = s.rfind("}")
                    if first != -1 and last != -1 and last > first:
                        json_str = s[first:last+1]
                        # Clean up common JSON errors: trailing commas before ] or }
                        import re
                        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
                        try:
                            data = json.loads(json_str)
                        except Exception:
                            pass

        if not isinstance(data, dict) or "facts" not in data:
            raise RuntimeError(f"Unable to parse LLM response as JSON with key 'facts'. Raw response: {response!r}")

        return list(dict.fromkeys(data["facts"]))  # dedupe

    def _prompt(self, topic, snippets):
        blocks = []
        for s in snippets:
            blocks.append(
                f"[{s.source.upper()}]\nTitle: {s.title}\nText: {s.text}"
            )

        return f"""
Extract 3–5 VERIFIED facts.

Rules:
- <= 150 words each
- No overlap
- No opinions
- No storytelling
- Atomic facts only

Topic: {topic}

Sources:
{chr(10).join(blocks)}

Return JSON only:
{{ "facts": [] }}
"""

