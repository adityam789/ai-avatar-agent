"""Script stage: prompt contract, word budget enforcement and TTS sanitising."""

import pytest

from ai_avatar.config import load_config
from ai_avatar.errors import LLMError
from ai_avatar.llm.fake import FakeLLM
from ai_avatar.stages.script import generate_script, sanitize_for_tts, trim_to_words


@pytest.fixture
def cfg():
    return load_config(environ={})  # target_seconds=18 -> 45 words, accepted range 34-56


def sentence_words(n, label="w"):
    """A sentence of exactly n words."""
    return " ".join(f"{label}{i}" for i in range(n - 1)) + f" {label}end."


class ScriptedLLM:
    """Returns queued replies and records prompts."""

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0)


def test_prompt_follows_marker_contract(cfg):
    llm = ScriptedLLM(sentence_words(45))
    cfg = cfg.model_copy(deep=True)
    cfg.script.tone = "dry and witty"
    generate_script("Black holes", ["They bend light.", "Spaghettification\nis real."], cfg, llm)
    prompt = llm.prompts[0]
    assert "TASK: write_script" in prompt.splitlines()
    assert "Topic: Black holes" in prompt.splitlines()
    assert [ln for ln in prompt.splitlines() if ln.startswith("- ")] == [
        "- They bend light.",
        "- Spaghettification is real.",
    ]
    assert "dry and witty" in prompt and "18 seconds" in prompt and "45 words" in prompt


def test_in_budget_reply_is_used_with_a_single_call(cfg):
    llm = ScriptedLLM(sentence_words(45))
    assert len(generate_script("t", ["f"], cfg, llm).split()) == 45
    assert len(llm.prompts) == 1


@pytest.mark.parametrize("count", [34, 56])
def test_budget_boundaries_are_inclusive(cfg, count):
    llm = ScriptedLLM(sentence_words(count))
    assert len(generate_script("t", ["f"], cfg, llm).split()) == count
    assert len(llm.prompts) == 1


def test_too_long_reply_triggers_one_corrective_retry(cfg):
    llm = ScriptedLLM(sentence_words(120), sentence_words(44))
    script = generate_script("t", ["f"], cfg, llm)
    assert len(script.split()) == 44
    assert len(llm.prompts) == 2
    assert "120 words" in llm.prompts[1] and "too long" in llm.prompts[1] and "between 34 and 56" in llm.prompts[1]
    assert llm.prompts[1].startswith(llm.prompts[0])


def test_too_short_reply_triggers_retry_and_short_retry_is_kept(cfg):
    llm = ScriptedLLM(sentence_words(10), sentence_words(20))
    assert len(generate_script("t", ["f"], cfg, llm).split()) == 20  # cannot pad; accepted after one retry
    assert "too short" in llm.prompts[1]


def test_still_too_long_after_retry_is_trimmed_at_sentence_boundary(cfg):
    long_reply = " ".join(sentence_words(20, label) for label in ("a", "b", "c", "d"))  # 80 words, 4 sentences
    llm = ScriptedLLM(long_reply, long_reply)
    script = generate_script("t", ["f"], cfg, llm)
    assert len(llm.prompts) == 2
    assert len(script.split()) == 40  # two whole sentences (a third would make 60 > 56)
    assert script == f"{sentence_words(20, 'a')} {sentence_words(20, 'b')}"
    assert "c0" not in script


def test_budget_scales_with_target_seconds(cfg):
    cfg = cfg.model_copy(deep=True)
    cfg.script.target_seconds = 8  # 20 words, accepted 15-25
    llm = ScriptedLLM(sentence_words(45), sentence_words(20))
    assert len(generate_script("t", ["f"], cfg, llm).split()) == 20
    assert "about 20 words" in llm.prompts[0]


def test_llm_reply_is_sanitised(cfg):
    reply = "**Wow!** 🚀 " + sentence_words(40) + " (pause) 'Quoted' [music]"
    script = generate_script("t", ["f"], cfg, ScriptedLLM(reply))
    assert "*" not in script and "🚀" not in script and "(" not in script and "[" not in script and "'" not in script
    assert script.startswith("Wow!")


def test_empty_reply_raises(cfg):
    with pytest.raises(LLMError, match="no usable"):
        generate_script("t", ["f"], cfg, ScriptedLLM("  🚀  ", "(silence)"))


def test_llm_errors_propagate(cfg):
    def failing(prompt):
        raise LLMError("boom")

    with pytest.raises(LLMError, match="boom"):
        generate_script("t", ["f"], cfg, failing)


def test_offline_default_uses_fake_llm_within_budget(cfg):
    cfg = cfg.model_copy(update={"offline": True})
    script = generate_script("Black holes", ["They bend light."], cfg)
    assert "Black holes" in script
    assert 34 <= len(script.split()) <= 56
    assert script == generate_script("Black holes", ["They bend light."], cfg, FakeLLM())


def test_no_facts_still_produces_a_prompt(cfg):
    llm = ScriptedLLM(sentence_words(45))
    generate_script("t", [], cfg, llm)
    assert "(none provided)" in llm.prompts[0]


def test_prompt_template_ships_as_package_data():
    from importlib import resources

    assert resources.files("ai_avatar").joinpath("prompts", "script.md").is_file()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("# Title\n\nSome **bold** and *italic* and `code`.", "Title Some bold and italic and code."),
        ("- first point\n- second point\n1. third", "first point second point third"),
        ("Read [this link](https://x.example/a?b=c) now.", "Read this link now."),
        ("Space is big 🌌🚀 really✨ big.", "Space is big really big."),
        ("He paused (dramatic pause) and spoke [music fades in].", "He paused and spoke."),
        ('She said "hello" and “goodbye”.', "She said hello and goodbye."),
        ("It's 'quoted' and don’t stop, dogs' bones.", "It's quoted and don't stop, dogs bones."),
        ("Here is the script:\nStars are hot.", "Stars are hot."),
        ("Narration: Stars are hot.", "Stars are hot."),
        ("Line one.\n\n\n  Line   two.\t", "Line one. Line two."),
        ("Trending #space and C# rocks", "Trending space and C# rocks"),
        ("   ", ""),
    ],
)
def test_sanitize_for_tts(raw, expected):
    assert sanitize_for_tts(raw) == expected


def test_trim_keeps_whole_sentences_and_hard_cuts_a_single_long_one():
    text = f"{sentence_words(5, 'a')} {sentence_words(5, 'b')} {sentence_words(5, 'c')}"
    assert trim_to_words(text, 10) == f"{sentence_words(5, 'a')} {sentence_words(5, 'b')}"
    assert trim_to_words(text, 100) == text
    cut = trim_to_words("one two three four five six, seven", 6)
    assert cut == "one two three four five six."
