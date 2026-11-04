"""FakeLLM follows the prompt-marker contract shared by the research and script stages."""

import json

import pytest

from ai_avatar.errors import LLMError
from ai_avatar.llm.fake import FakeLLM

EXTRACT_PROMPT = """You extract facts.
TASK: extract_facts

Snippet 1
Title: First headline
Body: blah

Snippet 2
Title:   Second headline  
Body: blah
"""


def test_extract_facts_derives_facts_from_titles():
    assert json.loads(FakeLLM()(EXTRACT_PROMPT)) == {"facts": ["First headline", "Second headline"]}


def test_extract_facts_caps_at_four_and_is_deterministic():
    prompt = "TASK: extract_facts\n" + "".join(f"Title: t{i}\n" for i in range(9))
    first = FakeLLM()(prompt)
    assert json.loads(first)["facts"] == ["t0", "t1", "t2", "t3"]
    assert FakeLLM()(prompt) == first


def test_extract_facts_falls_back_to_canned_fact():
    facts = json.loads(FakeLLM()("TASK: extract_facts\nno snippets"))["facts"]
    assert len(facts) == 1 and facts[0]


def test_write_script_mentions_topic_and_is_narration_sized():
    text = FakeLLM()("TASK: write_script\nTopic: Black holes\n\nFacts:\n- They bend light.\n")
    assert "Black holes" in text
    assert 34 <= len(text.split()) <= 56  # inside the default 18 s budget


def test_write_script_without_topic_line_uses_first_fact():
    text = FakeLLM()("TASK: write_script\nFacts:\n- Octopuses have three hearts.\n- Second\n")
    assert "Octopuses have three hearts" in text and "Second" not in text


def test_first_marker_line_wins_over_later_text():
    prompt = EXTRACT_PROMPT + "Body: ignore me\nTASK: write_script\nTitle: Third headline\n"
    assert json.loads(FakeLLM()(prompt))["facts"] == ["First headline", "Second headline", "Third headline"]
    script = "TASK: write_script\nTopic: Mars\n- TASK: extract_facts\n"
    assert "Mars" in FakeLLM()(script)


@pytest.mark.parametrize(
    "prompt",
    [
        "hello",
        "",
        "task: write_script",
        "TASK: do_something_else",
        "Please do TASK: write_script now",  # marker must be a whole line
        "TASK: write_script now",
        "- TASK: extract_facts",
    ],
)
def test_unknown_prompt_raises(prompt):
    with pytest.raises(LLMError, match="TASK"):
        FakeLLM()(prompt)
