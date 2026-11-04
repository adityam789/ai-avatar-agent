"""ResearchAgent and run_research: caching, source bookkeeping, error cases, offline end-to-end."""

import json
import logging
import threading
import time

import pytest
import requests

import ai_avatar.research as research
from ai_avatar.config import load_config
from ai_avatar.errors import LLMError, ResearchError
from ai_avatar.research import ResearchAgent, run_research
from ai_avatar.research.aggregator import LLMAggregator
from ai_avatar.research.cache import DiskResearchCache
from ai_avatar.research.collectors.base import SourceCollector
from ai_avatar.research.schemas import RawSnippet


class Fixed(SourceCollector):
    def __init__(self, name, snippets=(), error=None):
        self.name, self.snippets, self.error, self.calls = name, list(snippets), error, 0

    def collect(self, topic):
        self.calls += 1
        if self.error:
            raise self.error
        return self.snippets


class StubLLM:
    """Follows the prompt contract: one fact per `Title: ` line (max 4), like the real FakeLLM does."""

    def __init__(self):
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        assert "TASK: extract_facts" in prompt.splitlines()
        titles = [line[len("Title: ") :] for line in prompt.splitlines() if line.startswith("Title: ")]
        return json.dumps({"facts": titles[:4] or ["canned fact"]})


def agent_for(collectors, llm=None, cache=None):
    return ResearchAgent(collectors, LLMAggregator(llm or StubLLM()), cache)


def test_failing_collector_is_isolated_and_remaining_sources_are_used(caplog):
    good = Fixed("rss", [RawSnippet("rss", "Owl facts", "text", "https://a.test/owls")])
    bad = Fixed("reddit", error=requests.ConnectionError("down"))
    with caplog.at_level(logging.WARNING):
        bundle = agent_for([bad, good]).run("owls")
    assert bundle.facts == ["Owl facts"] and bundle.sources == ["rss"] and bundle.freshness == "fresh"
    assert "reddit collector failed" in caplog.text


def test_hung_collector_is_cut_off_and_the_others_still_contribute(caplog):
    class Hangs(SourceCollector):
        name = "web_search"
        release = threading.Event()

        def collect(self, topic):
            self.release.wait(10)
            return [RawSnippet("web_search", "too late", "", "https://late.test")]

    good = Fixed("rss", [RawSnippet("rss", "Owl facts", "text", "https://a.test/owls")])
    agent = ResearchAgent([Hangs(), good], LLMAggregator(StubLLM()), collector_timeout=0.2)
    start = time.monotonic()
    with caplog.at_level(logging.WARNING):
        bundle = agent.run("owls")
    elapsed = time.monotonic() - start
    Hangs.release.set()
    assert elapsed < 3
    assert bundle.facts == ["Owl facts"] and bundle.sources == ["rss"]
    assert "web_search collector timed out" in caplog.text


def test_run_research_passes_the_configured_timeout_to_every_collector(tmp_path, monkeypatch):
    cfg = load_config(
        environ={
            "AI_AVATAR__research__cache_dir": str(tmp_path / "cache"),
            "AI_AVATAR__research__timeout_seconds": "0.2",
            "AI_AVATAR__research__collectors": "[rss]",
        }
    )
    release = threading.Event()

    class Hangs(SourceCollector):
        name = "rss"

        def collect(self, topic):
            release.wait(10)
            return []

    monkeypatch.setattr(research, "build_llm", lambda cfg: StubLLM())
    monkeypatch.setattr(research, "build_collectors", lambda cfg: [Hangs()])
    start = time.monotonic()
    with pytest.raises(ResearchError, match="no snippets collected"):
        run_research("owls", cfg)
    release.set()
    assert time.monotonic() - start < 3


def test_all_collectors_failing_raises_a_clear_research_error(caplog):
    collectors = [Fixed("rss", error=OSError("x")), Fixed("web_search", error=ValueError("y")), Fixed("reddit")]
    llm = StubLLM()
    with pytest.raises(ResearchError, match=r"no snippets collected for 'owls'.*rss, web_search, reddit.*--offline"):
        agent_for(collectors, llm).run("owls")
    assert llm.prompts == []  # the LLM is not asked to invent facts from nothing


def test_no_collectors_enabled_is_reported_as_such():
    with pytest.raises(ResearchError, match="none enabled"):
        agent_for([]).run("owls")


def test_sources_record_urls_after_deduplication():
    a = RawSnippet("rss", "Owls", "t", "https://a.test/owls")
    dup = RawSnippet("web_search", "Owls (copy)", "t", "https://www.a.test/owls/")
    b = RawSnippet("web_search", "Barn owls", "t", "https://b.test/barn")
    bundle = agent_for([Fixed("rss", [a]), Fixed("web_search", [dup, b])]).run("owls")
    assert bundle.sources == ["rss", "web_search"]
    assert bundle.source_links == [
        {"source": "rss", "title": "Owls", "url": "https://a.test/owls"},
        {"source": "web_search", "title": "Barn owls", "url": "https://b.test/barn"},
    ]


def test_second_run_is_served_from_cache_without_collecting_or_calling_the_llm(tmp_path):
    collector = Fixed("rss", [RawSnippet("rss", "Owls", "t", "https://a.test")])
    llm = StubLLM()
    cache = DiskResearchCache(tmp_path)
    first = agent_for([collector], llm, cache).run("owls")
    second = agent_for([collector], llm, cache).run("owls")
    assert (first.freshness, second.freshness) == ("fresh", "cached")
    assert second.facts == first.facts and second.source_links == first.source_links
    assert collector.calls == 1 and len(llm.prompts) == 1


def test_expired_cache_entry_triggers_a_new_collection(tmp_path):
    now = [1_700_000_000.0]
    collector = Fixed("rss", [RawSnippet("rss", "Owls", "t", "https://a.test")])
    cache = DiskResearchCache(tmp_path, ttl_hours=1, clock=lambda: now[0])
    agent_for([collector], cache=cache).run("owls")
    now[0] += 1800
    assert agent_for([collector], cache=cache).run("owls").freshness == "cached"
    now[0] += 1800
    assert agent_for([collector], cache=cache).run("owls").freshness == "fresh"
    assert collector.calls == 2


def test_unusable_llm_reply_surfaces_as_llm_error_and_is_not_cached(tmp_path):
    cache = DiskResearchCache(tmp_path)
    collector = Fixed("rss", [RawSnippet("rss", "Owls", "t", "https://a.test")])
    with pytest.raises(LLMError):
        agent_for([collector], lambda prompt: "sorry, no", cache).run("owls")
    assert cache.find("owls") is None


# --- run_research wiring ---


@pytest.fixture
def offline_cfg(tmp_path, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("offline research must not touch the network")

    monkeypatch.setattr(requests, "get", no_network)
    env = {"AI_AVATAR__offline": "true", "AI_AVATAR__research__cache_dir": str(tmp_path / "cache")}
    return load_config(environ=env)


def test_offline_run_produces_facts_from_the_bundled_fixtures_with_no_keys(offline_cfg, monkeypatch, tmp_path):
    for name in ("GOOGLE_API_KEY", "GOOGLE_CSE_ID", "REDDIT_CLIENT_ID", "OPEN_ROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    llm = StubLLM()
    monkeypatch.setattr(research, "build_llm", lambda cfg: llm)
    bundle = run_research("anything at all", offline_cfg)
    assert bundle.freshness == "fresh"
    assert 1 <= len(bundle.facts) <= 4
    assert bundle.sources == ["rss", "web_search", "reddit"]
    urls = [link["url"] for link in bundle.source_links]
    assert len(urls) == len(set(urls)) == 5  # the web_search fixture holds one duplicate of an rss URL
    assert all(u.startswith("https://example.com/") for u in urls)
    assert not (tmp_path / "cache").exists()  # offline results never touch the cache
    assert json.dumps(bundle, default=lambda o: o.__dict__)  # serialisable for research.json


def test_offline_run_with_a_missing_fixtures_dir_explains_how_to_recover(offline_cfg, monkeypatch, tmp_path):
    offline_cfg.research.fixtures_dir = tmp_path / "nowhere"
    monkeypatch.setattr(research, "build_llm", lambda cfg: StubLLM())
    with pytest.raises(ResearchError, match="no snippets collected"):
        run_research("owls", offline_cfg)


def test_online_run_uses_a_disk_cache_under_the_configured_dir(tmp_path, monkeypatch):
    cfg = load_config(
        environ={
            "AI_AVATAR__research__cache_dir": str(tmp_path / "cache"),
            "AI_AVATAR__research__collectors": "[web_search]",
            "AI_AVATAR__research__search_provider": "static",
            "AI_AVATAR__research__fixtures_dir": str(research_fixtures()),
        }
    )
    monkeypatch.setattr(research, "build_llm", lambda cfg: StubLLM())
    assert run_research("owls", cfg).freshness == "fresh"
    assert len(list((tmp_path / "cache").glob("*_owls.json"))) == 1
    assert run_research("owls", cfg).freshness == "cached"


def research_fixtures():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent / "fixtures" / "research"
