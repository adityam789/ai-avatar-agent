"""JSON salvage for LLM replies."""

import pytest

from ai_avatar.llm.json_utils import extract_json_object


@pytest.mark.parametrize(
    "reply",
    [
        '{"facts": ["a", "b"]}',
        'Sure! Here you go:\n{"facts": ["a", "b"]}\nHope that helps.',
        '```json\n{"facts": ["a", "b"]}\n```',
        '{"facts": ["a", "b",],}',
        'Note {not json} first. Then {"facts": ["a", "b"]} and a stray } at the end',
        'Result:\n```\n{"facts": ["a", "b"],}\n```\nDone {really}.',
    ],
)
def test_salvages_object_from_messy_replies(reply):
    assert extract_json_object(reply) == {"facts": ["a", "b"]}


def test_commas_inside_strings_survive_when_json_is_valid():
    assert extract_json_object('{"facts": ["a,]", "b,}"]}') == {"facts": ["a,]", "b,}"]}


@pytest.mark.parametrize("reply", ["", "no json here", "[1, 2, 3]", '{"facts": [', "{broken: yes}"])
def test_raises_value_error_when_nothing_parses(reply):
    with pytest.raises(ValueError):
        extract_json_object(reply)
