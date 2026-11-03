"""Minimal chat-completions client for OpenRouter or any OpenAI-compatible endpoint.

Point ``llm.base_url`` at the endpoint's ``/chat/completions`` URL and list model names in ``llm.models``
(for example a local Ollama or vLLM server, or OpenAI itself). Two layers of resilience:

* with more than one model, the request carries OpenRouter's ``models`` array, so OpenRouter itself falls
  through to the next model when one is rate-limited or down (other servers ignore the extra field);
* the client retries 429, 5xx and network timeouts with exponential backoff.

Anything that is not a well-formed completion raises :class:`~ai_avatar.errors.LLMError`; raw HTTP bodies are
never returned to callers.
"""

import logging
import time
from collections.abc import Callable

import requests

from ai_avatar.errors import LLMError
from ai_avatar.redact import scrub

log = logging.getLogger(__name__)

API_KEY_ENV = "OPEN_ROUTER_API_KEY"
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_BACKOFF_BASE_SECONDS = 1.0
_MAX_DETAIL_CHARS = 200


class LLMClient:
    """Callable ``client(prompt) -> str`` returning the assistant message text."""

    def __init__(
        self,
        models: list[str],
        base_url: str,
        api_key: str,
        *,
        max_retries: int = 3,
        timeout_seconds: float = 120.0,
        referer: str | None = None,
        title: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """``max_retries`` counts retries after the first attempt; ``sleep`` is injectable for tests."""
        if not models:
            raise LLMError("No LLM models configured: set llm.models in the config.")
        self.models = list(models)
        self.base_url = base_url
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self._sleep = sleep
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        if referer:
            self._headers["HTTP-Referer"] = referer  # optional OpenRouter attribution
        if title:
            self._headers["X-Title"] = title

    def __call__(self, prompt: str) -> str:
        if "Authorization" not in self._headers:
            raise LLMError(f"{API_KEY_ENV} is not set. Put it in .env (see .env.example) or export it.")
        payload: dict = {"model": self.models[0], "messages": [{"role": "user", "content": prompt}]}
        if len(self.models) > 1:
            payload["models"] = self.models  # OpenRouter tries these in order
        response = self._post_with_retries(payload)
        return _extract_text(response)

    def _post_with_retries(self, payload: dict) -> requests.Response:
        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                response = requests.post(self.base_url, headers=self._headers, json=payload, timeout=self.timeout_seconds)
            except (requests.Timeout, requests.ConnectionError) as exc:
                problem = f"network error: {scrub(exc)}"
            except requests.RequestException as exc:
                raise LLMError(f"LLM request failed: {scrub(exc)}") from exc
            else:
                if response.status_code < 400:
                    return response
                problem = f"HTTP {response.status_code}{_error_detail(response)}"
                if response.status_code not in _RETRY_STATUSES:
                    raise LLMError(f"LLM request failed ({problem}).{_auth_hint(response.status_code)}")
            if attempt == attempts:
                raise LLMError(f"LLM request failed after {attempts} attempts (last: {problem}).")
            delay = _BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
            log.warning("LLM attempt %d/%d failed (%s); retrying in %.1fs", attempt, attempts, problem, delay)
            self._sleep(delay)
        raise AssertionError("unreachable")  # the loop always returns or raises


def _error_detail(response: requests.Response) -> str:
    """Short, scrubbed ``error.message`` from a JSON error body, or '' (the body is never echoed verbatim)."""
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return ""
    if not isinstance(message, str):
        return ""
    return f": {scrub(message)[:_MAX_DETAIL_CHARS]}"


def _auth_hint(status: int) -> str:
    return f" Check {API_KEY_ENV}." if status in (401, 403) else ""


def _extract_text(response: requests.Response) -> str:
    """Pull ``choices[0].message.content`` out of a completion, or raise :class:`LLMError`."""
    try:
        data = response.json()
    except ValueError as exc:
        raise LLMError("LLM returned a response that is not JSON.") from exc
    if isinstance(data, dict) and isinstance(data.get("error"), dict):  # some gateways return errors with HTTP 200
        raise LLMError(f"LLM returned an error{_error_detail(response)}")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("LLM response is missing choices[0].message.content.") from exc
    if not isinstance(content, str) or not content.strip():
        raise LLMError("LLM returned an empty message.")
    return content
