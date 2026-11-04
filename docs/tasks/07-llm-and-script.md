# 07 — LLM client + script agent

## Goal
A small, reliable, provider-agnostic LLM layer and a script generator with better prompting.

## Context
- `LLMClient` posts to OpenRouter with a single `:free` model (rotates/throttles). Auth header is sent even when key is empty (`""`). Response parsing is overly permissive; falls back to returning raw HTTP text.
- `script.py` asks for "15–20 seconds" but nothing checks length; no sanitation for TTS (emoji, markdown, stage directions).

## Steps
1. `llm/client.py`: `LLMClient(models: list[str], base_url, api_key)`; use OpenRouter's `models` array fallback AND client-side retry with exponential backoff on 429/5xx/timeouts (max 3). Fail fast with a clear error if key missing. Never fall back to returning raw response text — raise `LLMError`.
2. Make model list + base_url configurable in config (works with any OpenAI-compatible endpoint, document this). Keep the OpenRouter headers (`HTTP-Referer`, `X-Title`) optional.
3. Add a `FakeLLM` for tests/offline mode that returns canned JSON facts / a canned script.
4. `stages/script.py`: prompt template in a separate file (`prompts/script.md`) with variables (topic, facts, target_seconds, tone). Enforce word budget (~2.5 words/sec -> 40–55 words for 15–20s): count words, and if outside ±25%, retry once with a corrective instruction, else trim at sentence boundary.
5. Post-process for TTS: strip markdown, emojis, parenthetical stage directions, quotes; collapse whitespace.
6. Save `script.txt` into the run dir.

## Acceptance criteria
- Unit tests with mocked `requests` for: retry on 429, fallback models, missing key error, malformed response.
- Script word-count enforcement test.

## Results (2026-11-03)

**Done**
- `llm/client.py`: `LLMClient(models, base_url, api_key, *, max_retries, timeout_seconds, referer, title, sleep)`. Works with any
  OpenAI-compatible chat-completions endpoint (set `llm.base_url` + `llm.models`; documented in the module docstring). With more than one
  model the payload carries OpenRouter's `models` fallback array; the client also retries 429/500/502/503/504 and timeouts/connection
  errors with exponential backoff (1 s, 2 s, 4 s...). `llm.max_retries` counts retries after the first attempt (3 -> up to 4 requests).
  Other 4xx fail immediately (401/403 hint at `OPEN_ROUTER_API_KEY`). Responses must contain a non-empty `choices[0].message.content`,
  otherwise `LLMError`; the legacy `response` field and the "return raw text" fallback are gone. A JSON `error` body on HTTP 200 is an
  `LLMError`. All error text goes through `redact.scrub`; only a short `error.message` is quoted, never the raw body; headers are not logged.
- Missing key: the client sends no `Authorization` header and raises `LLMError` naming `OPEN_ROUTER_API_KEY` on the first call, before any
  request. `OPEN_ROUTER_REFERER` / `OPEN_ROUTER_TITLE` are optional headers. Import-time `load_dotenv()` removed (the CLI loads `.env`).
- `llm/__init__.py`: `build_llm(cfg)` returns `FakeLLM` when `cfg.offline`, else an `LLMClient` from `cfg.llm` + environment.
- `llm/fake.py`: `FakeLLM` implements the shared marker contract (`TASK: extract_facts` -> JSON facts from `Title: ` lines, max 4;
  `TASK: write_script` -> canned ~45-word narration naming the `Topic:` line, else first `- ` fact; anything else -> `LLMError`).
- `stages/script.py` + `prompts/script.md` (package data, added to `pyproject.toml`): template variables topic/facts/target words/seconds/tone.
  Word budget = `target_seconds * 2.5` +-25% (18 s -> 45 words, accepted 34-56). Out of range -> one retry with a corrective note appended;
  still too long -> trimmed at a sentence boundary (hard cut if one sentence exceeds the budget); still too short -> kept with a warning
  (cannot be padded honestly). `sanitize_for_tts` strips leading "Here is the script:" labels, markdown, emoji, `(...)`/`[...]` asides, double
  quotes and single-quote marks (apostrophes kept), hashtags, and collapses whitespace. Saving `script.txt` stays in `pipeline.py`'s adapter.

**Verified**
- `pytest` in a fresh venv (`pip install -e ".[dev]"`): 146 passed, 1 skipped, 1 deselected. New: `tests/test_llm_client.py` (mocked
  `requests.post`: retry on 429/5xx with backoff, gives up, timeout, no retry on 401, fallback `models` payload, missing key sends nothing,
  8 malformed shapes, scrubbing, `build_llm`), `tests/test_llm_fake.py`, `tests/test_script_stage.py` (prompt contract, budget boundaries,
  retry, trim, sanitizer table). Mutation check: disabling the non-retryable-status branch fails 2 tests.
- A non-editable `pip install --target` of the worktree contains `ai_avatar/prompts/script.md`.
- `ruff check --line-length 120` is clean on the files touched (no ruff config exists yet; Task 09).

**Not verified**: any real OpenRouter call (no network/key by rule).

**Deviations / notes**
- Model fallback: see "Review round 1 fixes" (server-side `models` array on openrouter.ai only, client-side loop elsewhere).
- `tests/test_research_live.py` still calls `LLMClient()` with no arguments (old signature); it is an integration test owned by Task 06.

**Open questions for Aditya**
- Should `llm.max_retries: 3` mean 3 retries (4 requests, current) or 3 total attempts?
- Should the CLI warn when `llm.models` contains only a single `:free` model (these rotate/throttle)?

**Review round 1 fixes**
- Sanitizer: a leading label is stripped only when it ends the first line (no more eating text up to a later colon); stage-direction
  parentheticals (allow-list, `[...]`, `(*...*)`) are removed, ordinary ones keep their words without the parentheses; markdown markers are
  stripped only when paired (`snake_case` survives); `#1` -> "number 1", `~50` -> "about 50"; U+20E3 handled; unclosed `(` never survives.
- `trim_to_words(text, max, min=0)` hard-cuts at `max` words when whole sentences leave fewer than `min` ("Wow.", "Dr."), without doubling
  final punctuation. The corrective retry now only wins if its word count is closer to the target. Budgets round half-up.
- Client: `models` array only for `*.openrouter.ai`; elsewhere models are tried one by one (after retries are exhausted, or on 404).
  Retries cover 408/425/429/5xx, honour `Retry-After` (capped at 30 s), and treat an HTTP 200 body with `error.code` like that status.
  Constructor key is masked in every message and log line, request errors are raised `from None`, blank keys count as missing, no
  `AssertionError` path. `llm.max_retries >= 0` and `llm.timeout_seconds > 0` are validated in `LLMConfig` (and in the client).
- `FakeLLM` uses the first whole-line `TASK: <name>` marker; the script prompt no longer says "(none provided)" and collapses topic whitespace.

**Review round 2 fixes**
- Client: the server's `error.message` is masked (environment key and constructor key) before it is truncated to 200 chars, so a key
  straddling the cut can no longer survive in part. Exponential backoff is capped at 30 s like `Retry-After`. Long lines wrapped.
- Script stage: if the first draft is out of budget but non-empty and the corrective retry raises `LLMError`, the first draft is kept
  (trimmed if too long) and a scrubbed warning is logged; an empty first draft with a failing retry still raises.
- Draft selection compares each draft's word count after `trim_to_words` against the target (a 5-word draft no longer beats a
  100-word retry that trims to the budget).
- Sanitizer: `2*3*4` becomes "2 times 3 times 4" and `5 * 3` "5 times 3"; `*`/`**` is stripped as emphasis only when paired around
  non-space text and not inside a word; `~$5` / `~-3` read "about $5" / "about -3".
- Tests: key at the truncation point (constructor and environment key), parametrized host spoofing for the `models` array, capped
  backoff, hard-cut punctuation, failed retry (both cases), trimmed-length draft selection, new sanitizer rows. Each fix was
  mutation-checked (reverted, tests failed). Suite: 213 passed.
