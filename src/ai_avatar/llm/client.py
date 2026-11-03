"""Minimal chat-completions client for OpenRouter or any OpenAI-compatible endpoint.

Point ``llm.base_url`` at the endpoint's ``/chat/completions`` URL and list model names in ``llm.models``
(for example a local Ollama or vLLM server, or OpenAI itself). Two layers of resilience:

* model fallback: on openrouter.ai one request carries OpenRouter's ``models`` array and OpenRouter falls through
  the list itself; on any other host the ``models`` field is not sent (strict servers reject unknown fields) and
  the client tries the models one after another when a model keeps failing or is not found;
* retries: HTTP 408, 425, 429 and 5xx, network errors and timeouts, and HTTP 200 responses whose body is an
  error with such a code (OpenRouter reports upstream failures this way), with exponential backoff or the
  server's ``Retry-After`` (both capped at 30 s).

Anything that is not a well-formed completion raises :class:`~ai_avatar.errors.LLMError`; raw HTTP bodies are
never returned to callers, and the API key is masked in every message the client builds.
"""

import logging
import time
from collections.abc import Callable
from urllib.parse import urlparse

import requests

from ai_avatar.errors import LLMError
from ai_avatar.redact import scrub

log = logging.getLogger(__name__)

API_KEY_ENV = "OPEN_ROUTER_API_KEY"
_RETRY_STATUSES = frozenset({408, 425, 429})  # plus every 5xx, see _is_retryable
_MODEL_MISSING_STATUS = 404
_BACKOFF_BASE_SECONDS = 1.0
_MAX_RETRY_AFTER_SECONDS = 30.0  # also caps the exponential backoff
_MAX_DETAIL_CHARS = 200
_MIN_KEY_LEN = 6  # same rule as ai_avatar.redact


class _ModelFailed(LLMError):
    """One model is unusable (retries exhausted or model not found); the next configured model may work."""


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
        if max_retries < 0 or timeout_seconds <= 0:
            raise LLMError("llm.max_retries must be >= 0 and llm.timeout_seconds must be > 0.")
        self.models = list(models)
        self.base_url = base_url
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self._sleep = sleep
        self._api_key = (api_key or "").strip()
        self._headers = {"Content-Type": "application/json"}
        if self._api_key:
            self._headers["Authorization"] = f"Bearer {self._api_key}"
        if referer:
            self._headers["HTTP-Referer"] = referer  # optional OpenRouter attribution
        if title:
            self._headers["X-Title"] = title

    def __call__(self, prompt: str) -> str:
        if "Authorization" not in self._headers:
            raise LLMError(f"{API_KEY_ENV} is not set. Put it in .env (see .env.example) or export it.")
        if len(self.models) > 1 and self._is_openrouter():
            payload = self._payload(prompt, self.models[0])
            payload["models"] = self.models  # OpenRouter tries these in order
            return _extract_text(self._post_with_retries(payload))
        last: LLMError | None = None
        for model in self.models:
            try:
                return _extract_text(self._post_with_retries(self._payload(prompt, model)))
            except _ModelFailed as exc:
                last = exc
                log.warning("LLM model %s failed (%s)", model, exc)
        if len(self.models) == 1:
            raise last
        raise LLMError(f"All {len(self.models)} LLM models failed; last error: {last}") from None

    def _is_openrouter(self) -> bool:
        host = urlparse(self.base_url).hostname or ""
        return host == "openrouter.ai" or host.endswith(".openrouter.ai")

    @staticmethod
    def _payload(prompt: str, model: str) -> dict:
        return {"model": model, "messages": [{"role": "user", "content": prompt}]}

    def _scrub(self, text: object) -> str:
        """``scrub`` plus the key this client was constructed with (it may not be in the environment)."""
        out = scrub(text)
        return out.replace(self._api_key, "***") if len(self._api_key) >= _MIN_KEY_LEN else out

    def _post_with_retries(self, payload: dict) -> requests.Response:
        attempts = self.max_retries + 1
        attempt = 0
        while True:
            attempt += 1
            retry_after = None
            try:
                response = requests.post(
                    self.base_url, headers=self._headers, json=payload, timeout=self.timeout_seconds
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                problem = self._scrub(f"network error: {exc}")
            except requests.RequestException as exc:
                log.warning("LLM request failed: %s", self._scrub(exc))
                raise LLMError(f"LLM request failed: {self._scrub(exc)}") from None  # the cause may embed the URL
            else:
                status = _failure_status(response)
                if status is None:
                    return response
                label = f"HTTP {status}"
                if status != response.status_code:
                    label = f"HTTP {response.status_code} with error code {status}"
                problem = self._scrub(f"{label}{_error_detail(response, self._scrub)}")
                if status == _MODEL_MISSING_STATUS:
                    raise _ModelFailed(f"LLM request failed ({problem}). Check llm.models.")
                if not _is_retryable(status):
                    raise LLMError(f"LLM request failed ({problem}).{_auth_hint(status)}")
                retry_after = _retry_after_seconds(response)
            if attempt == attempts:
                raise _ModelFailed(f"LLM request failed after {attempts} attempts (last: {problem}).")
            delay = min(_BACKOFF_BASE_SECONDS * 2 ** (attempt - 1), _MAX_RETRY_AFTER_SECONDS)
            if retry_after is not None:
                delay = retry_after
            log.warning("LLM attempt %d/%d failed (%s); retrying in %.1fs", attempt, attempts, problem, delay)
            self._sleep(delay)


def _is_retryable(status: int) -> bool:
    return status in _RETRY_STATUSES or 500 <= status < 600


def _failure_status(response: requests.Response) -> int | None:
    """The status to act on, or None for a good response.

    That is the HTTP status when it is >= 400, or the numeric ``error.code`` of an HTTP 200 whose body is an
    error object (0 when the code is missing, which counts as a non-retryable failure).
    """
    if response.status_code >= 400:
        return response.status_code
    try:
        error = response.json()["error"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(error, dict):
        return None
    try:
        return int(error.get("code", 0))
    except (TypeError, ValueError):
        return 0


def _retry_after_seconds(response: requests.Response) -> float | None:
    """The ``Retry-After`` header in seconds (capped), or None if absent or not a number (HTTP dates are ignored)."""
    try:
        seconds = float(response.headers.get("Retry-After", ""))
    except (TypeError, ValueError):
        return None
    return min(seconds, _MAX_RETRY_AFTER_SECONDS) if seconds >= 0 else None  # also rejects NaN


def _error_detail(response: requests.Response, mask: Callable[[object], str]) -> str:
    """Short ``error.message`` from a JSON error body, or ''. It is masked first, then truncated, so a secret
    straddling the cut cannot survive in part (the body is never echoed verbatim)."""
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return ""
    if not isinstance(message, str):
        return ""
    return f": {mask(message)[:_MAX_DETAIL_CHARS]}"


def _auth_hint(status: int) -> str:
    return f" Check {API_KEY_ENV}." if status in (401, 403) else ""


def _extract_text(response: requests.Response) -> str:
    """Pull ``choices[0].message.content`` out of a completion, or raise :class:`LLMError`."""
    try:
        data = response.json()
    except ValueError as exc:
        raise LLMError("LLM returned a response that is not JSON.") from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("LLM response is missing choices[0].message.content.") from exc
    if not isinstance(content, str) or not content.strip():
        raise LLMError("LLM returned an empty message.")
    return content
