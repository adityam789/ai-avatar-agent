"""Aggregator: prompt contract, token budget, dedup, response validation."""

import json
import logging

import pytest

from ai_avatar.errors import LLMError
from ai_avatar.research.aggregator import FactList, LLMAggregator, dedupe_snippets, fit_budget
from ai_avatar.research.schemas import RawSnippet


def snip(title="T", text="body", url="", source="rss"):
    return RawSnippet(source, title, text, url)


class StubLLM:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def test_prompt_follows_the_marker_contract():
    llm = StubLLM({"facts": ["one"]})
    LLMAggregator(llm).aggregate("owls", [snip("First"), snip("Second", source="web_search")])
    lines = llm.prompts[0].splitlines()
    assert "TASK: extract_facts" in lines
    assert [line for line in lines if line.startswith("Title: ")] == ["Title: First", "Title: Second"]
    assert '"facts"' in llm.prompts[0] and "Topic: owls" in lines


def test_prompt_is_logged_at_debug_not_printed(caplog, capsys):
    caplog.set_level(logging.DEBUG, logger="ai_avatar.research.aggregator")
    LLMAggregator(StubLLM({"facts": ["one"]})).aggregate("owls", [snip()])
    assert capsys.readouterr().out == ""
    assert any("TASK: extract_facts" in r.message for r in caplog.records)


def test_budget_truncates_long_snippets_and_keeps_every_title():
    snippets = [snip(f"Title {i}", "x" * 5000) for i in range(4)]
    llm = StubLLM({"facts": ["f"]})
    LLMAggregator(llm, max_chars=1000).aggregate("t", snippets)
    prompt = llm.prompts[0]
    assert prompt.count("Title: Title ") == 4
    assert prompt.count("x") <= 1000
    assert len(prompt) < 1000 + 600  # budget plus the fixed instructions


def test_budget_gives_unused_space_of_short_snippets_to_later_ones():
    fitted = fit_budget([snip("a", "short"), snip("b", "y" * 5000)], max_chars=1000)
    assert fitted[0] == ("a", "short")
    assert len(fitted[1][0]) + len(fitted[1][1]) == 1000 - len("a") - len("short")


def test_budget_never_exceeds_limit_even_with_tiny_budget():
    fitted = fit_budget([snip("t" * 300, "x" * 300)] * 5, max_chars=50)
    assert sum(len(t) + len(x) for t, x in fitted) <= 50


def test_dedupe_by_url_and_by_title():
    a = snip("Owls are great", url="https://www.example.com/owls/")
    same_url = snip("Different title", url="http://example.com/owls#section")
    same_title = snip("OWLS   are great!", url="https://other.org/x")
    other = snip("Something else", url="https://other.org/y")
    no_url_1, no_url_2 = snip("Untitled one"), snip("Untitled two")
    assert dedupe_snippets([a, same_url, same_title, other, no_url_1, no_url_2]) == [a, other, no_url_1, no_url_2]


def test_facts_are_cleaned_and_deduplicated():
    llm = StubLLM({"facts": ["  one ", "two", "one", "", "two"]})
    assert LLMAggregator(llm).aggregate("t", [snip()]) == ["one", "two"]


def test_reply_wrapped_in_prose_is_salvaged():
    llm = StubLLM('Here: ```json\n{"facts": ["one", "two",]}\n```')
    assert LLMAggregator(llm).aggregate("t", [snip()]) == ["one", "two"]


@pytest.mark.parametrize("count,ok", [(0, False), (1, True), (8, True), (9, False)])
def test_fact_count_must_be_between_1_and_8(count, ok):
    facts = [f"fact {i}" for i in range(count)]
    if ok:
        assert FactList(facts=facts).facts == facts
        assert LLMAggregator(StubLLM({"facts": facts})).aggregate("t", [snip()]) == facts
    else:
        with pytest.raises(LLMError, match="facts"):
            LLMAggregator(StubLLM({"facts": facts})).aggregate("t", [snip()])


@pytest.mark.parametrize(
    "reply", ["not json", '{"other": ["a"]}', '{"facts": "a string"}', '{"facts": [1, 2]}', '{"facts": [" "]}']
)
def test_unusable_replies_raise_llm_error_with_a_hint(reply):
    with pytest.raises(LLMError, match="did not return JSON"):
        LLMAggregator(StubLLM(reply)).aggregate("t", [snip()])


def test_error_does_not_leak_secret_urls_from_the_reply(monkeypatch):
    with pytest.raises(LLMError) as err:
        LLMAggregator(StubLLM("see https://x.test/?key=SECRETVALUE123")).aggregate("t", [snip()])
    assert "SECRETVALUE123" not in str(err.value)
