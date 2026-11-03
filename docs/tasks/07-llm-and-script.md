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
