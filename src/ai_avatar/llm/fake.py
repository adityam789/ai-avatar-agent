"""Deterministic stand-in for the LLM, used by ``--offline`` runs and tests (no network, no API key).

It recognises the ``TASK: <name>`` marker line that the research and script prompts carry. Only the first marker
line counts and it must be a whole line, so snippet or fact text cannot send a prompt to the wrong task.
"""

import json
import re

from ai_avatar.errors import LLMError

_CANNED_FACT = "This is a canned offline fact used because no snippets were provided."
_MAX_FACTS = 4
_TASK_LINE = re.compile(r"^TASK: (\w+)[ \t\r]*$", re.MULTILINE)
_SCRIPT_TEMPLATE = (
    "Here is a quick look at {subject}. It matters because it keeps changing how people think about the world "
    "around them. Researchers and everyday observers keep finding new details, and each one adds context to the "
    "story. Stay curious, check the sources, and see where the evidence leads next."
)


class FakeLLM:
    """Callable ``fake(prompt) -> str`` that answers the two known tasks and rejects anything else."""

    def __call__(self, prompt: str) -> str:
        marker = _TASK_LINE.search(prompt)
        task = marker.group(1) if marker else None
        if task == "extract_facts":
            titles = re.findall(r"^Title: (.+)$", prompt, flags=re.MULTILINE)
            facts = [t.strip() for t in titles if t.strip()][:_MAX_FACTS] or [_CANNED_FACT]
            return json.dumps({"facts": facts})
        if task == "write_script":
            return _SCRIPT_TEMPLATE.format(subject=_script_subject(prompt))
        raise LLMError("FakeLLM only understands prompts containing 'TASK: extract_facts' or 'TASK: write_script'.")


def _script_subject(prompt: str) -> str:
    """The topic if the prompt has a ``Topic:`` line, else the first ``- `` fact, else a generic phrase."""
    for pattern in (r"^Topic: (.+)$", r"^- (.+)$"):
        match = re.search(pattern, prompt, flags=re.MULTILINE)
        if match and match.group(1).strip():
            return match.group(1).strip().rstrip(".")
    return "today's topic"
