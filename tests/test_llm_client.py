"""LLM client: retries, fallbacks, key handling and response validation, with ``requests.post`` mocked."""

import pytest
import requests

from ai_avatar.config import load_config
from ai_avatar.errors import LLMError
from ai_avatar.llm import FakeLLM, LLMClient, build_llm

URL = "https://llm.example/v1/chat/completions"


class FakeResponse:
    def __init__(self, status=200, body=None, json_error=False):
        self.status_code = status
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


def make_client(sleeps=None, models=("m1",), key="sk-test-key-123", **kwargs):
    return LLMClient(list(models), URL, key, sleep=(sleeps if sleeps is not None else []).append, **kwargs)


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


def test_model_fallback_list_is_sent_to_the_endpoint(post):
    post.queue = [ok()]
    make_client(models=("primary", "backup-1", "backup-2"))("x")
    payload = post.calls[0][1]["json"]
    assert payload["model"] == "primary"
    assert payload["models"] == ["primary", "backup-1", "backup-2"]


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
    cfg.llm.base_url = URL
    cfg.llm.max_retries = 1
    cfg.llm.timeout_seconds = 9
    post.queue = [ok("from env")]
    llm = build_llm(cfg)
    assert isinstance(llm, LLMClient)
    assert llm("x") == "from env"
    url, kwargs = post.calls[0]
    assert url == URL and kwargs["timeout"] == 9 and kwargs["json"]["models"] == ["a", "b"]
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
