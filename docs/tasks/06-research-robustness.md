# 06 — Research agent robustness + pluggable search

## Goal
Research survives dead services. Each source is optional, failures are logged not fatal, and the search provider is swappable.

## Context
- Google Custom Search JSON API: closed to new customers, discontinued 2027-01-01.
- Reddit Data API now requires approval; collector must be optional.
- `GoogleCSECollector` has no error handling (`resp.json()` on a 403 yields no items silently or KeyError on `item["title"]`).
- `RedditCollector.__init__` builds praw eagerly -> crashes without creds.
- `aggregator.py` prints the whole prompt; cache is in-memory only; docstrings are stale ("de-duplication by URL" etc.).
- RSS collector fetches 3 feeds sequentially with no timeout, matches topic by substring.

## Steps
1. Collector contract: `collect(topic) -> list[RawSnippet]`, must never raise for expected failures; wrap in `safe_collect` that logs a warning and returns `[]`. Add per-collector timeout.
2. Make collectors registry-based and config-enabled: `research.collectors: [rss, web_search, reddit]`. Reddit only constructed if creds present and `reddit` extra installed.
3. Rename `GoogleCSECollector` -> `WebSearchCollector` with a provider interface (`SearchProvider.search(q, n)`): implement `GoogleCSEProvider` (kept, marked deprecated in docstring + README) and one additional provider that works without Google. Preferred: `DuckDuckGoProvider` via the `ddgs` package (no key) OR `BraveSearchProvider` (API key env `BRAVE_API_KEY`). Pick one, add as optional extra. Also implement a `StaticProvider` for tests/offline demos reading JSON fixtures.
4. Add a `fixtures/` offline mode (`--offline`) so the project can be demoed with no network or keys.
5. Cache: disk-backed JSON cache in `.cache/research/` keyed by slug+date, TTL configurable (default 24h). Keep the in-memory class behind the same interface.
6. Aggregator: remove `print`; use logging at DEBUG; truncate snippets to a token budget; keep JSON salvage logic but move to `llm/json_utils.py` with unit tests; validate with pydantic (`facts: list[str]`, 1–8 items).
7. Dedup snippets by URL/title before prompting; record sources with URLs in `research.json` (currently only source *names* are stored).
8. Fix docstrings.

## Acceptance criteria
- Running with zero keys + `--offline` produces facts from fixtures.
- Running with all collectors failing yields a clear `ResearchError` ("no snippets collected"), not a stack trace.
- Unit tests cover: JSON salvage, collector failure isolation, cache TTL, RSS topic filtering.

## Open questions
- Which replacement provider to ship as default (DuckDuckGo vs Brave)? Default to DuckDuckGo (no key) unless owner objects.
