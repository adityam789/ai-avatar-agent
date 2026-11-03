"""Collectors: failure isolation, RSS topic filtering, search providers, registry. No real network."""

import logging
import sys
import threading
import time
import types

import pytest
import requests

from ai_avatar.config import load_config
from ai_avatar.errors import ConfigError, ResearchError
from ai_avatar.research.collectors import build_collectors
from ai_avatar.research.collectors.base import SourceCollector, safe_collect
from ai_avatar.research.collectors.fixture import FixtureCollector
from ai_avatar.research.collectors.reddit import RedditCollector
from ai_avatar.research.collectors.rss import RSSCollector, matches_topic
from ai_avatar.research.collectors.search_providers import (
    DuckDuckGoProvider,
    GoogleCSEProvider,
    SearchResult,
    StaticProvider,
)
from ai_avatar.research.collectors.web_search import WebSearchCollector
from ai_avatar.research.schemas import RawSnippet

SECRET = "AIzaSECRETKEY123456"


def make_cfg(**env):
    return load_config(environ={f"AI_AVATAR__{k}": v for k, v in env.items()})


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("GOOGLE_API_KEY", "GOOGLE_CSE_ID", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"):
        monkeypatch.delenv(name, raising=False)


# --- failure isolation ---


class Boom(SourceCollector):
    name = "boom"

    def __init__(self, exc):
        self.exc = exc

    def collect(self, topic):
        raise self.exc


def test_safe_collect_returns_empty_list_and_logs_a_scrubbed_warning(caplog, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", SECRET)
    exc = requests.HTTPError(f"403 for url: https://api.test/search?key={SECRET}&q=owls")
    with caplog.at_level(logging.WARNING):
        assert safe_collect(Boom(exc), "owls") == []
    assert "boom collector failed" in caplog.text and "HTTPError" in caplog.text
    assert SECRET not in caplog.text


def test_safe_collect_passes_results_through():
    class Fine(SourceCollector):
        name = "fine"

        def collect(self, topic):
            return [RawSnippet("fine", topic, "")]

    assert [s.title for s in safe_collect(Fine(), "owls")] == ["owls"]


class Nameless(SourceCollector):
    """A subclass that forgot to set ``name`` (it is only an annotation on the base class)."""

    def __init__(self, exc):
        self.exc = exc

    def collect(self, topic):
        raise self.exc


def test_safe_collect_survives_a_collector_without_a_name(caplog, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", SECRET)
    with caplog.at_level(logging.WARNING):
        assert safe_collect(Nameless(RuntimeError(f"bad key {SECRET}")), "owls") == []
    assert "Nameless collector failed" in caplog.text and "RuntimeError" in caplog.text
    assert SECRET not in caplog.text


class Hangs(SourceCollector):
    name = "hangs"

    def __init__(self):
        self.release = threading.Event()
        self.started = threading.Event()

    def collect(self, topic):
        self.started.set()
        self.release.wait(10)
        return [RawSnippet("hangs", "too late", "")]


def test_safe_collect_enforces_a_wall_clock_timeout(caplog):
    hung = Hangs()
    start = time.monotonic()
    with caplog.at_level(logging.WARNING):
        assert safe_collect(hung, "owls", timeout=0.2) == []
    assert time.monotonic() - start < 2
    assert hung.started.is_set() and "hangs collector timed out after 0.2s" in caplog.text
    hung.release.set()  # let the abandoned worker finish


def test_safe_collect_without_timeout_waits_for_the_collector():
    class Slow(SourceCollector):
        name = "slow"

        def collect(self, topic):
            time.sleep(0.2)
            return [RawSnippet("slow", topic, "")]

    assert [s.title for s in safe_collect(Slow(), "owls")] == ["owls"]
    assert [s.title for s in safe_collect(Slow(), "owls", timeout=5)] == ["owls"]


def test_abandoned_collector_runs_in_a_daemon_thread():
    hung = Hangs()
    safe_collect(hung, "owls", timeout=0.1)
    worker = next(t for t in threading.enumerate() if t.name == "collect-hangs")
    assert worker.daemon  # cannot keep the interpreter alive at exit
    hung.release.set()
    worker.join(2)


# --- RSS ---


@pytest.mark.parametrize(
    "topic,text,expected",
    [
        ("rust", "Rust 2.0 is out", True),
        ("rust", "Why trust matters", False),  # substring, not a word
        ("AI", "He said it was fine", False),
        ("AI", "New AI chips announced", True),
        ("black hole", "Black holes: new images", True),  # plural
        ("quantum computing", "Computing news only", False),  # all words needed
        ("what are black holes", "Black holes: new images", True),  # stopwords ignored
        ("is rust fast", "Rust is fast", True),
        ("can rust do async", "Async Rust news", True),  # "can", "do" are stopwords
        ("what does rust do", "Rust 2.0 is out", True),  # "does" must not be folded to "doe" and survive
        ("the", "the end", True),  # only stopwords: fall back to the words themselves
        ("", "anything", False),
    ],
)
def test_matches_topic_uses_whole_words(topic, text, expected):
    assert matches_topic(topic, text) is expected


FEED = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Rust 2.0 released</title><link>https://a.test/rust</link>
<description>&lt;p&gt;The &lt;b&gt;Rust&lt;/b&gt; team shipped it &amp;amp; more&lt;/p&gt;</description></item>
<item><title>Why trust matters in startups</title><link>https://a.test/trust</link>
<description>no mention</description></item>
<item><title>Gardening tips</title><link>https://a.test/garden</link>
<description>Grow tomatoes with rust-colored soil?</description></item>
</channel></rss>"""


class FakeResponse:
    def __init__(self, content=b"", status=200, json_data=None):
        self.content, self.status_code, self._json = content, status, json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json


def test_rss_filters_by_whole_word_strips_html_and_sets_timeout(monkeypatch):
    seen = []

    def fake_get(url, timeout=None, **kw):
        seen.append((url, timeout))
        return FakeResponse(FEED.encode())

    monkeypatch.setattr(requests, "get", fake_get)
    snippets = RSSCollector(["https://feed.test/a"], timeout=3.5).collect("rust")
    assert seen == [("https://feed.test/a", 3.5)]
    assert [s.title for s in snippets] == ["Rust 2.0 released", "Gardening tips"]  # "trust" is not "rust"
    first = snippets[0]
    assert first.text == "The Rust team shipped it & more" and first.url == "https://a.test/rust"
    assert first.source == "rss"


def test_rss_filters_before_capping_so_older_matching_entries_are_found(monkeypatch):
    unrelated = "".join(f"<item><title>Gardening {i}</title><description>x</description></item>" for i in range(8))
    old_hit = "<item><title>Old Rust story</title><link>https://a.test/old</link><description>x</description></item>"
    feed = f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{unrelated}{old_hit}</channel></rss>'
    monkeypatch.setattr(requests, "get", lambda url, timeout=None, **kw: FakeResponse(feed.encode()))
    assert [s.title for s in RSSCollector(["https://x.test/f"]).collect("rust")] == ["Old Rust story"]


def test_rss_takes_at_most_entries_per_feed_matching_items(monkeypatch):
    items = "".join(f"<item><title>Rust {i}</title><description>x</description></item>" for i in range(9))
    feed = f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{items}</channel></rss>'
    monkeypatch.setattr(requests, "get", lambda url, timeout=None, **kw: FakeResponse(feed.encode()))
    snippets = RSSCollector(["https://x.test/f"]).collect("rust")
    assert [s.title for s in snippets] == [f"Rust {i}" for i in range(5)]


def test_rss_one_dead_feed_does_not_lose_the_others(monkeypatch, caplog):
    def fake_get(url, timeout=None, **kw):
        if "dead" in url:
            raise requests.ConnectionError("no route")
        return FakeResponse(FEED.encode())

    monkeypatch.setattr(requests, "get", fake_get)
    with caplog.at_level(logging.WARNING):
        snippets = RSSCollector(["https://dead.test/f", "https://ok.test/f"]).collect("rust")
    assert len(snippets) == 2
    assert "dead.test" in caplog.text


def test_rss_http_error_status_skips_feed(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, timeout=None, **kw: FakeResponse(FEED.encode(), status=503))
    assert RSSCollector(["https://x.test/f"]).collect("rust") == []


# --- search providers ---


def test_google_cse_maps_items_and_skips_ones_without_title(monkeypatch):
    seen = {}

    def fake_get(url, params=None, timeout=None):
        seen.update(params=params, timeout=timeout)
        items = [{"title": "A", "snippet": "sa", "link": "https://a"}, {"snippet": "no title"}, {"title": "B"}]
        return FakeResponse(json_data={"items": items})

    monkeypatch.setattr(requests, "get", fake_get)
    results = GoogleCSEProvider("k", "cx", timeout=4).search("owls", 20)
    assert results == [SearchResult("A", "sa", "https://a"), SearchResult("B", "", "")]
    assert seen["timeout"] == 4 and seen["params"]["num"] == 10  # the API caps num at 10


def test_google_cse_without_items_key_is_just_empty(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(json_data={"searchInformation": {}}))
    assert GoogleCSEProvider("k", "cx").search("owls", 5) == []


def test_google_cse_http_error_body_becomes_research_error(monkeypatch):
    body = {"error": {"message": "This project does not have access to Custom Search JSON API."}}
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(status=403, json_data=body))
    with pytest.raises(ResearchError, match="HTTP 403: This project does not have access"):
        GoogleCSEProvider("k", "cx").search("owls", 5)


def test_google_cse_never_leaks_the_api_key_through_a_failing_request(monkeypatch, caplog):
    monkeypatch.setenv("GOOGLE_API_KEY", SECRET)

    def fake_get(url, params=None, timeout=None):
        raise requests.ConnectionError(f"HTTPSConnectionPool: Max retries exceeded with url: /v1?key={SECRET}&q=owls")

    monkeypatch.setattr(requests, "get", fake_get)
    collector = WebSearchCollector(GoogleCSEProvider(SECRET, "cx"))
    with caplog.at_level(logging.DEBUG):
        assert safe_collect(collector, "owls") == []
        with pytest.raises(ResearchError) as err:
            collector.collect("owls")
    assert SECRET not in caplog.text and SECRET not in str(err.value)
    assert err.value.__cause__ is None and err.value.__suppress_context__  # original exception is not chained


def test_google_cse_from_env_needs_both_variables(monkeypatch):
    assert GoogleCSEProvider.from_env() is None
    monkeypatch.setenv("GOOGLE_API_KEY", SECRET)
    assert GoogleCSEProvider.from_env() is None
    monkeypatch.setenv("GOOGLE_CSE_ID", "cx")
    assert GoogleCSEProvider.from_env() is not None


def test_duckduckgo_provider_uses_ddgs(monkeypatch):
    calls = {}

    class FakeDDGS:
        def __init__(self, timeout=None, **kw):
            calls["timeout"] = timeout

        def text(self, query, max_results=None, **kw):
            calls.update(query=query, max_results=max_results)
            return [{"title": "T", "body": "B", "href": "https://h"}, {"body": "untitled"}]

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FakeDDGS))
    assert DuckDuckGoProvider(timeout=7).search("owls", 3) == [SearchResult("T", "B", "https://h")]
    assert calls == {"timeout": 7, "query": "owls", "max_results": 3}


def test_duckduckgo_timeout_is_rounded_up_never_to_zero(monkeypatch):
    calls = {}

    class FakeDDGS:
        def __init__(self, timeout=None, **kw):
            calls["timeout"] = timeout

        def text(self, query, max_results=None, **kw):
            return []

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FakeDDGS))
    DuckDuckGoProvider(timeout=0.5).search("owls", 3)
    assert calls["timeout"] == 1
    DuckDuckGoProvider(timeout=2.2).search("owls", 3)
    assert calls["timeout"] == 3


def test_duckduckgo_without_ddgs_installed_explains_the_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "ddgs", None)  # makes `from ddgs import DDGS` raise ImportError
    with pytest.raises(ResearchError, match=r"ai-avatar-agent\[search\]"):
        DuckDuckGoProvider().search("owls", 3)


def test_static_provider_and_web_search_collector(tmp_path):
    path = tmp_path / "web.json"
    path.write_text('[{"title": "A", "text": "ta", "url": "u1"}, {"title": "B"}, {"title": "C"}]')
    snippets = WebSearchCollector(StaticProvider(path), num_results=2).collect("anything")
    assert [(s.source, s.title, s.text, s.url) for s in snippets] == [
        ("web_search", "A", "ta", "u1"),
        ("web_search", "B", "", ""),
    ]
    assert snippets[0].metadata == {"provider": "static"}


def test_static_provider_rejects_non_list_fixture(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"title": "A"}')
    with pytest.raises(ValueError, match="JSON list"):
        StaticProvider(path).search("x", 5)


# --- Reddit ---


def _fake_praw(posts):
    class Sub:
        def search(self, topic, limit):
            return posts

    class Reddit:
        def __init__(self, **kw):
            Reddit.kwargs = kw

        def subreddit(self, name):
            return Sub()

    return types.SimpleNamespace(Reddit=Reddit)


def test_reddit_collector_filters_unpopular_posts_and_passes_timeout(monkeypatch):
    def post(title, score, comments):
        return types.SimpleNamespace(title=title, score=score, num_comments=comments, selftext="body", url="https://r")

    praw = _fake_praw([post("popular", 500, 40), post("quiet", 5, 1)])
    monkeypatch.setitem(sys.modules, "praw", praw)
    collector = RedditCollector("id", "secret", "agent", timeout=2)
    assert praw.Reddit.kwargs["requestor_kwargs"] == {"timeout": 2}
    snippets = collector.collect("owls")
    assert {s.title for s in snippets} == {"popular"} and len(snippets) == 4  # one per subreddit
    assert snippets[0].metadata["score"] == 580


# --- registry ---


def names(collectors):
    return [c.name for c in collectors]


def test_default_config_skips_reddit_without_credentials():
    collectors = build_collectors(make_cfg())
    assert names(collectors) == ["rss", "web_search"]
    assert collectors[1].provider.name == "duckduckgo"


def test_reddit_is_built_when_credentials_and_praw_exist(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret-value")
    monkeypatch.setenv("REDDIT_USER_AGENT", "agent")
    monkeypatch.setitem(sys.modules, "praw", _fake_praw([]))
    assert names(build_collectors(make_cfg())) == ["rss", "web_search", "reddit"]


def test_reddit_is_skipped_when_praw_is_missing(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret-value")
    monkeypatch.setenv("REDDIT_USER_AGENT", "agent")
    monkeypatch.setitem(sys.modules, "praw", None)
    assert names(build_collectors(make_cfg())) == ["rss", "web_search"]


def test_google_cse_provider_needs_keys_else_web_search_is_skipped(monkeypatch):
    cfg = make_cfg(research__search_provider="google_cse")
    assert names(build_collectors(cfg)) == ["rss"]
    monkeypatch.setenv("GOOGLE_API_KEY", SECRET)
    monkeypatch.setenv("GOOGLE_CSE_ID", "cx")
    collectors = build_collectors(cfg)
    assert collectors[1].provider.name == "google_cse"


def test_collector_list_in_config_is_respected():
    assert names(build_collectors(make_cfg(research__collectors="[rss]"))) == ["rss"]
    assert build_collectors(make_cfg(research__collectors="[]")) == []


def test_unknown_collector_name_is_a_clear_config_error():
    cfg = make_cfg()
    cfg.research.collectors = ["rss", "twitter"]  # config validation normally rejects this; the registry must too
    with pytest.raises(ConfigError, match="unknown research collector 'twitter'.*rss, web_search, reddit"):
        build_collectors(cfg)
    cfg.offline = True
    with pytest.raises(ConfigError, match="twitter"):
        build_collectors(cfg)


def test_unknown_collector_name_is_rejected_when_loading_config():
    with pytest.raises(ValueError, match="twitter"):  # pydantic ValidationError
        make_cfg(research__collectors="[twitter]")


def test_static_search_provider_reads_fixtures_dir(tmp_path):
    (tmp_path / "web_search.json").write_text('[{"title": "A"}]')
    cfg = make_cfg(research__search_provider="static", research__fixtures_dir=str(tmp_path))
    web = build_collectors(cfg)[1]
    assert [s.title for s in web.collect("x")] == ["A"]


def test_offline_mode_replaces_every_collector_with_a_fixture_reader(monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("offline mode must not touch the network")

    monkeypatch.setattr(requests, "get", no_network)
    collectors = build_collectors(make_cfg(offline="true"))
    assert names(collectors) == ["rss", "web_search", "reddit"]
    assert all(isinstance(c, FixtureCollector) for c in collectors)
    assert all(safe_collect(c, "any topic") for c in collectors)  # bundled fixtures exist for each
