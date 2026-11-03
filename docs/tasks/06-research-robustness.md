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

## Results (2026-11-03)

### What was done
- **Collector contract**: `SourceCollector.collect(topic) -> list[RawSnippet]` may raise; `safe_collect` (in `collectors/base.py`) wraps every
  collector, logs a warning through `scrub` and returns `[]`. HTTP calls have a timeout (`research.timeout_seconds`); RSS now downloads each
  feed with `requests` (feedparser has no timeout) and skips only the dead feed.
- **Registry**: `build_collectors(cfg)` builds what `research.collectors` lists. Reddit is only built when all three `REDDIT_*` variables are set
  and `praw` is installed (otherwise logged and skipped); `RedditCollector` no longer crashes at import/construct time without creds.
- **Pluggable search**: `GoogleCSECollector` became `WebSearchCollector(provider)`; providers in `collectors/search_providers.py`:
  `DuckDuckGoProvider` (default, `ddgs`, new `search` extra), `GoogleCSEProvider` (deprecated; request errors are re-raised without the original
  exception so the `?key=` URL never reaches logs/`run.json`; non-200 answers become a `ResearchError` with Google's message) and `StaticProvider`
  (JSON fixture). **Default provider: DuckDuckGo** (no key), as the task proposed.
- **Offline mode**: with `cfg.offline` every enabled collector is replaced by a `FixtureCollector` reading `fixtures/research/<collector>.json`
  (new files `rss.json`, `web_search.json`, `reddit.json`; one deliberate duplicate URL demonstrates dedup). The LLM still runs (FakeLLM in the merged
  code). Offline runs bypass the cache.
- **Cache**: `ResearchCache` (in-memory) and `DiskResearchCache` (`<cache_dir>/<UTC date>_<slug>.json`) share `find(topic)` / `store(bundle)`, take
  `ttl_hours` and an injectable `clock`; expired, corrupt or other-topic entries are misses. Cached bundles come back with `freshness="cached"`.
- **Aggregator**: no more `print` (prompt logged at DEBUG); prompt contains `TASK: extract_facts` and `Title: ` lines; snippets are de-duplicated by
  normalised URL/title (`dedupe_snippets`) and trimmed to `research.max_snippet_chars` (`fit_budget`, characters stand in for tokens); the reply is
  parsed with `llm/json_utils.extract_json_object` and validated by a pydantic `FactList` (1-8 distinct non-empty strings) -> `LLMError` with a hint
  otherwise. The prompt tells the model to treat snippets as untrusted data.
- **RSS topic filter**: whole-word match of every significant topic word (plural "s" folded, small stopword list), HTML stripped from summaries.
- **Sources**: `ResearchBundle` gained `source_links` (`{"source", "title", "url"}` per snippet used) next to the existing `sources` names, so
  `research.json` records URLs without changing the existing `ResearchBundle(topic, facts, "fresh", ["rss"])` call sites.
- `ResearchError("no snippets collected for '<topic>' (collectors tried: ...). ... run with --offline.")` when everything fails or is disabled.
- Removed the live test `tests/test_research_live.py`; `.cache/` added to `.gitignore`.

### How verified
- `pytest` (whole suite): 176 passed, 1 skipped, no network (tests monkeypatch `requests.get`, inject fake `ddgs`/`praw` modules, and a stub LLM).
- `ruff check --line-length 120 --select E,F,I,UP,B` on the touched files: clean.
- Mutation spot-checks: breaking the cache expiry comparison or the RSS word-boundary match makes 8 tests fail.
- New tests: `tests/test_json_utils.py`, `tests/test_research_{aggregator,agent,cache,collectors}.py`.

### Not verified
- Real DuckDuckGo / RSS / Google / Reddit calls (no network allowed); `ddgs` call signature (`DDGS(timeout=...)`, `.text(query, max_results=...)`,
  result keys `title`/`body`/`href`) was taken from the installed package's API but never exercised live.
- `run_research` with the real `build_llm`/FakeLLM (task 07 is developed in parallel); tests inject a stub following the prompt marker contract.
- README still needs the "Google CSE is deprecated / use `pip install -e .[search]`" note (README is outside this task's file ownership).

### Deviations
- `ResearchCache.store` now takes a `ResearchBundle` (was `store(topic, facts, sources)`); nothing else used it.
- `reddit_creds_from_env` moved from `research/__init__.py` to `collectors/reddit.py` (no longer re-exported).
- `DiskResearchCache` leaves old date-stamped files in place (delete the directory to clear it); `ttl_hours: 0` disables caching.
- Token budget is counted in characters (`max_snippet_chars`), as the config field name implies; no tokenizer dependency.

### Open questions
- Keep DuckDuckGo (unofficial scraping via `ddgs`, can be rate limited) as default, or ship Brave Search (needs `BRAVE_API_KEY`)? Providers are one small class each.
- Should a cache hit still require an LLM key? Today `run_research` builds the LLM before checking the cache.

### Review round 1 fixes
- `safe_collect(collector, topic, timeout)` runs `collect` in a daemon thread and gives up after `research.timeout_seconds` of wall-clock time
  (warning, returns `[]`; the straggler cannot block the run or interpreter exit). `ResearchAgent(..., collector_timeout=)` / `run_research` pass it on.
  DuckDuckGo's timeout is `max(1, ceil(timeout))` instead of `int()` (0.5 became 0).
- `safe_collect` and the agent no longer assume a collector sets `name` (`collector_name()` falls back to the class name).
- `extract_json_object(text, want_key=None)`: objects are tried outermost-first with trailing-comma repair per object, and the first one containing
  `want_key` wins (the aggregator passes `"facts"`). Code-fence stripping was dropped (fences outside the object are skipped by the scan, and fences
  inside strings are no longer damaged).
- Disk cache writes go through a temp file + `os.replace`; an entry whose stored time is in the future (clock moved backwards) is a miss in both caches.
- Aggregator prompt: whitespace (newlines included) in titles, texts and the topic is collapsed, so snippets cannot forge `TASK:` / `Title: ` lines.
- RSS: the topic filter runs before the per-feed cap; stopword set extended ("is", "can", "do", "what", ...) and now compared in folded form
  (previously "does" was folded to "doe" and never matched). `build_collectors` raises `ConfigError` for unknown collector names.
- Dedup: by normalised URL when present, otherwise by `(source, title)`.
- Tests: new cases for every item above, including a hung collector (0.2 s timeout), a nameless collector with an env secret, atomic cache write and
  backwards clock. Verified they fail against the pre-fix source (22 failures) and pass now.
