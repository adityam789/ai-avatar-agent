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


def test_damaged_outer_object_beats_a_valid_inner_one():
    reply = '{"facts": ["a", "b",], "meta": {"x": 1}}'
    assert extract_json_object(reply) == {"facts": ["a", "b"], "meta": {"x": 1}}
    assert extract_json_object(reply, want_key="facts")["facts"] == ["a", "b"]


def test_want_key_prefers_the_object_that_has_it():
    reply = '{"note": "x"}\n{"facts": ["a"]}'
    assert extract_json_object(reply, want_key="facts") == {"facts": ["a"]}
    assert extract_json_object(reply) == {"note": "x"}  # without a key: first object
    assert extract_json_object('{"note": "x"}', want_key="facts") == {"note": "x"}  # no match: caller validates


def test_code_fences_inside_strings_are_left_alone():
    reply = '```json\n{"facts": ["use ```json fences", "b"]}\n```'
    assert extract_json_object(reply) == {"facts": ["use ```json fences", "b"]}


@pytest.mark.parametrize("reply", ["", "no json here", "[1, 2, 3]", '{"facts": [', "{broken: yes}"])
def test_raises_value_error_when_nothing_parses(reply):
    with pytest.raises(ValueError):
        extract_json_object(reply)
