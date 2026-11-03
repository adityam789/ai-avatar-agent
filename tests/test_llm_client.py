"""LLM client: retries, fallbacks, key handling and response validation, with ``requests.post`` mocked."""

import logging

import pytest
import requests
from pydantic import ValidationError

from ai_avatar.config import LLMConfig, load_config
from ai_avatar.errors import LLMError
from ai_avatar.llm import FakeLLM, LLMClient, build_llm

URL = "https://llm.example/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class FakeResponse:
    def __init__(self, status=200, body=None, json_error=False, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self._json_error = json_error
        self.text = "RAW-HTTP-TEXT-SHOULD-NEVER-LEAK"

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._body


def ok(text="hello"):
    return FakeResponse(200, {"choices": [{"message": {"content": text}}]})


@pytest.fixture
def post(monkeypatch):
    """Queue responses (or exceptions) for ``requests.post``; records every call."""

    class Post:
        def __init__(self):
            self.queue, self.calls = [], []

        def __call__(self, url, **kwargs):
            self.calls.append((url, kwargs))
            item = self.queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    fake = Post()
    monkeypatch.setattr(requests, "post", fake)
    return fake


def make_client(sleeps=None, models=("m1",), key="sk-test-key-123", url=URL, **kwargs):
    return LLMClient(list(models), url, key, sleep=(sleeps if sleeps is not None else []).append, **kwargs)


def test_success_sends_expected_request(post):
    post.queue = [ok("hi there")]
    client = make_client(timeout_seconds=7, referer="https://me.example", title="demo")
    assert client("say hi") == "hi there"
    url, kwargs = post.calls[0]
    assert url == URL
    assert kwargs["timeout"] == 7
    assert kwargs["json"] == {"model": "m1", "messages": [{"role": "user", "content": "say hi"}]}
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test-key-123"
    assert kwargs["headers"]["HTTP-Referer"] == "https://me.example"
    assert kwargs["headers"]["X-Title"] == "demo"


def test_optional_headers_omitted_by_default(post):
    post.queue = [ok()]
    make_client()("x")
    headers = post.calls[0][1]["headers"]
    assert "HTTP-Referer" not in headers and "X-Title" not in headers


def test_retries_on_429_with_exponential_backoff(post):
    post.queue = [FakeResponse(429), FakeResponse(503), ok("finally")]
    sleeps = []
    assert make_client(sleeps)("x") == "finally"
    assert len(post.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_gives_up_after_max_retries(post):
    post.queue = [FakeResponse(429, {"error": {"message": "slow down"}}) for _ in range(3)]
    sleeps = []
    with pytest.raises(LLMError, match="after 3 attempts.*429.*slow down"):
        make_client(sleeps, max_retries=2)("x")
    assert len(post.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_timeout_is_retried_then_reported(post):
    post.queue = [requests.Timeout("read timed out"), ok("recovered")]
    assert make_client()("x") == "recovered"
    post.queue = [requests.ConnectionError("down")] * 2
    with pytest.raises(LLMError, match="network error"):
        make_client(max_retries=1)("x")


def test_client_errors_are_not_retried(post):
    post.queue = [FakeResponse(401, {"error": {"message": "bad key"}})]
    sleeps = []
    with pytest.raises(LLMError, match=r"HTTP 401.*bad key.*OPEN_ROUTER_API_KEY"):
        make_client(sleeps)("x")
    assert len(post.calls) == 1 and sleeps == []


def test_openrouter_gets_the_models_array(post):
    post.queue = [ok()]
    make_client(models=("primary", "backup-1", "backup-2"), url=OPENROUTER_URL)("x")
    payload = post.calls[0][1]["json"]
    assert payload["model"] == "primary"
    assert payload["models"] == ["primary", "backup-1", "backup-2"]


def test_other_hosts_never_get_the_models_field_and_fall_back_client_side(post):
    post.queue = [
        FakeResponse(503),
        FakeResponse(503),
        FakeResponse(404, {"error": {"message": "no such model"}}),
        ok("third"),
    ]
    client = make_client(models=("m1", "m2", "m3"), max_retries=1)
    assert client("x") == "third"
    assert [call[1]["json"]["model"] for call in post.calls] == ["m1", "m1", "m2", "m3"]
    assert all("models" not in call[1]["json"] for call in post.calls)


def test_client_side_fallback_gives_up_when_every_model_fails(post):
    post.queue = [FakeResponse(503), FakeResponse(503)]
    with pytest.raises(LLMError, match="All 2 LLM models failed.*503"):
        make_client(models=("m1", "m2"), max_retries=0)("x")


def test_client_side_fallback_does_not_hide_fatal_errors(post):
    post.queue = [FakeResponse(401, {"error": {"message": "bad key"}})]
    with pytest.raises(LLMError, match="HTTP 401"):
        make_client(models=("m1", "m2"))("x")
    assert len(post.calls) == 1  # a bad key would fail the next model too


@pytest.mark.parametrize("status", [408, 425, 500, 502, 520, 524, 599])
def test_more_statuses_are_retried(post, status):
    post.queue = [FakeResponse(status), ok("ok")]
    assert make_client()("x") == "ok"


@pytest.mark.parametrize("status", [400, 401, 403, 422])
def test_other_client_errors_are_not_retried(post, status):
    post.queue = [FakeResponse(status)]
    with pytest.raises(LLMError):
        make_client()("x")
    assert len(post.calls) == 1


def test_retry_after_header_is_honoured_and_capped(post):
    post.queue = [
        FakeResponse(429, headers={"Retry-After": "7"}),
        FakeResponse(429, headers={"Retry-After": "9999"}),
        FakeResponse(503, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),  # HTTP-date: use backoff
        ok(),
    ]
    sleeps = []
    make_client(sleeps)("x")
    assert sleeps == [7.0, 30.0, 4.0]


def test_http_200_with_retryable_error_body_is_retried(post):
    post.queue = [FakeResponse(200, {"error": {"code": 502, "message": "upstream down"}}), ok("fine")]
    sleeps = []
    assert make_client(sleeps)("x") == "fine"
    assert sleeps == [1.0]


def test_http_200_with_fatal_error_body_is_not_retried(post):
    post.queue = [FakeResponse(200, {"error": {"code": 400, "message": "bad input"}})]
    with pytest.raises(LLMError, match="bad input"):
        make_client()("x")
    assert len(post.calls) == 1


def test_http_200_error_body_exhausts_retries(post):
    post.queue = [FakeResponse(200, {"error": {"code": 429, "message": "busy"}})] * 2
    with pytest.raises(LLMError, match="after 2 attempts.*busy"):
        make_client(max_retries=1)("x")


def test_zero_retries_means_one_attempt(post):
    post.queue = [FakeResponse(500)]
    with pytest.raises(LLMError, match="after 1 attempts"):
        make_client(max_retries=0)("x")


def test_invalid_retry_settings_are_rejected():
    for kwargs in ({"max_retries": -1}, {"timeout_seconds": 0}):
        with pytest.raises(LLMError, match="llm.max_retries"):
            make_client(**kwargs)
    with pytest.raises(ValidationError):
        LLMConfig(models=["m"], max_retries=-1)
    with pytest.raises(ValidationError):
        LLMConfig(models=["m"], timeout_seconds=0)


def test_blank_api_key_counts_as_missing(post):
    client = make_client(key="   \n")
    with pytest.raises(LLMError, match="OPEN_ROUTER_API_KEY"):
        client("x")
    assert post.calls == []
    assert make_client(key="  sk-padded-key-1\n")._headers["Authorization"] == "Bearer sk-padded-key-1"


def test_missing_key_fails_before_any_request(post):
    client = make_client(key="")
    assert "Authorization" not in client._headers
    with pytest.raises(LLMError, match="OPEN_ROUTER_API_KEY"):
        client("x")
    assert post.calls == []


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(200, json_error=True),
        FakeResponse(200, {"unexpected": "shape"}),
        FakeResponse(200, {"response": "legacy field is not accepted"}),
        FakeResponse(200, {"choices": []}),
        FakeResponse(200, {"choices": [{"message": {"content": "   "}}]}),
        FakeResponse(200, {"choices": [{"message": {"content": None}}]}),
        FakeResponse(200, {"error": {"message": "upstream exploded"}}),
        FakeResponse(200, ["not", "a", "dict"]),
    ],
)
def test_malformed_response_raises_without_leaking_raw_text(post, response):
    post.queue = [response]
    with pytest.raises(LLMError) as excinfo:
        make_client()("x")
    assert "RAW-HTTP-TEXT" not in str(excinfo.value)


def test_error_messages_are_scrubbed(post, monkeypatch):
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-super-secret-value")
    post.queue = [FakeResponse(400, {"error": {"message": "bad request near sk-super-secret-value"}})]
    with pytest.raises(LLMError) as excinfo:
        make_client()("x")
    assert "sk-super-secret-value" not in str(excinfo.value)
    post.queue = [requests.RequestException("failed: https://llm.example/x?key=abcdef123456")]
    with pytest.raises(LLMError) as excinfo:
        make_client()("x")
    assert "abcdef123456" not in str(excinfo.value)


def test_no_models_configured():
    with pytest.raises(LLMError, match="llm.models"):
        LLMClient([], URL, "k")


def test_build_llm_reads_config_and_environment(monkeypatch, post):
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-env-key-456")
    monkeypatch.setenv("OPEN_ROUTER_REFERER", "https://ref.example")
    monkeypatch.delenv("OPEN_ROUTER_TITLE", raising=False)
    cfg = load_config(environ={}).model_copy(deep=True)
    cfg.llm.models = ["a", "b"]
    cfg.llm.base_url = OPENROUTER_URL
    cfg.llm.max_retries = 1
    cfg.llm.timeout_seconds = 9
    post.queue = [ok("from env")]
    llm = build_llm(cfg)
    assert isinstance(llm, LLMClient)
    assert llm("x") == "from env"
    url, kwargs = post.calls[0]
    assert url == OPENROUTER_URL and kwargs["timeout"] == 9 and kwargs["json"]["models"] == ["a", "b"]
    assert kwargs["headers"]["Authorization"] == "Bearer sk-env-key-456"
    assert kwargs["headers"]["HTTP-Referer"] == "https://ref.example"
    assert "X-Title" not in kwargs["headers"]
    assert llm.max_retries == 1


def test_build_llm_without_key_errors_on_first_call(monkeypatch, post):
    monkeypatch.delenv("OPEN_ROUTER_API_KEY", raising=False)
    llm = build_llm(load_config(environ={}))
    with pytest.raises(LLMError, match="OPEN_ROUTER_API_KEY"):
        llm("x")
    assert post.calls == []


def test_build_llm_offline_returns_fake_and_ignores_env(monkeypatch, post):
    monkeypatch.delenv("OPEN_ROUTER_API_KEY", raising=False)
    cfg = load_config(environ={}).model_copy(update={"offline": True})
    llm = build_llm(cfg)
    assert isinstance(llm, FakeLLM)
    assert "TASK: write_script" not in llm("TASK: write_script\nTopic: x")  # returns narration, not the prompt
    assert post.calls == []


KEY = "sk-not-in-environment-789"  # deliberately never exported: only the constructor argument knows it


@pytest.fixture
def no_env_key(monkeypatch):
    monkeypatch.delenv("OPEN_ROUTER_API_KEY", raising=False)


def assert_key_free(excinfo, caplog=None):
    texts = [str(excinfo.value), repr(excinfo.value.__cause__)]
    if caplog is not None:
        texts.append(caplog.text)
    assert all(KEY not in text for text in texts), texts


def test_constructor_key_is_masked_in_http_error_detail(post, no_env_key):
    post.queue = [FakeResponse(400, {"error": {"message": f"invalid key {KEY}"}})]
    with pytest.raises(LLMError) as excinfo:
        make_client(key=KEY)("x")
    assert "***" in str(excinfo.value)
    assert_key_free(excinfo)


def test_constructor_key_is_masked_for_timeouts_giveup_and_warnings(post, no_env_key, caplog):
    caplog.set_level(logging.WARNING)
    post.queue = [requests.Timeout(f"timed out calling {URL}?x={KEY}")] * 2
    with pytest.raises(LLMError, match="last: network error") as excinfo:
        make_client(key=KEY, max_retries=1)("x")
    assert "retrying" in caplog.text  # the log.warning path ran
    assert_key_free(excinfo, caplog)


def test_giveup_message_masks_key_from_retryable_http_error(post, no_env_key, caplog):
    caplog.set_level(logging.WARNING)
    post.queue = [FakeResponse(503, {"error": {"message": f"overloaded for {KEY}"}})] * 2
    with pytest.raises(LLMError, match="last: HTTP 503") as excinfo:
        make_client(key=KEY, max_retries=1)("x")
    assert_key_free(excinfo, caplog)


def test_request_exception_cause_is_not_chained(post, no_env_key, caplog):
    caplog.set_level(logging.WARNING)
    post.queue = [requests.exceptions.InvalidURL(f"bad url https://llm.example/x/{KEY}")]
    with pytest.raises(LLMError) as excinfo:
        make_client(key=KEY)("x")
    assert excinfo.value.__cause__ is None and excinfo.value.__suppress_context__
    assert_key_free(excinfo, caplog)


def test_key_straddling_the_truncation_point_is_fully_masked(post, no_env_key):
    post.queue = [FakeResponse(400, {"error": {"message": "x" * 190 + KEY + " tail"}})]
    with pytest.raises(LLMError) as excinfo:
        make_client(key=KEY)("x")
    assert KEY[:6] not in str(excinfo.value)  # not even the part before the cut
    assert "***" in str(excinfo.value)


def test_environment_key_straddling_the_truncation_point_is_masked(post, monkeypatch):
    monkeypatch.setenv("OPEN_ROUTER_API_KEY", "sk-env-straddler-555")
    post.queue = [FakeResponse(400, {"error": {"message": "y" * 195 + "sk-env-straddler-555"}})]
    with pytest.raises(LLMError) as excinfo:
        make_client(key="unrelated-key-1")("x")
    assert "sk-env" not in str(excinfo.value)


@pytest.mark.parametrize(
    ("url", "sends_models"),
    [
        (OPENROUTER_URL, True),
        ("https://eu.openrouter.ai/api/v1/chat/completions", True),
        ("https://openrouter.ai.evil.com/api/v1/chat/completions", False),
        ("https://evil.com/openrouter.ai/api/v1/chat/completions", False),
        ("https://openrouter.ai@evil.com/api/v1/chat/completions", False),
        ("https://notopenrouter.ai/api/v1/chat/completions", False),
    ],
)
def test_models_array_is_only_sent_to_openrouter_hosts(post, url, sends_models):
    post.queue = [ok()]
    make_client(models=("a", "b"), url=url)("x")
    assert ("models" in post.calls[0][1]["json"]) is sends_models


def test_exponential_backoff_is_capped(post):
    post.queue = [FakeResponse(503)] * 8 + [ok()]
    sleeps = []
    make_client(sleeps, max_retries=8)("x")
    assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]
