# Owner questions & manual actions

Decisions and actions only Aditya can take. Each item notes the default chosen so work could continue.

## Manual actions
- [x] **Task 01** — Rotated the Reddit app secret and other keys (confirmed by owner 2026-11-03).
- [x] **Task 01** — History rewrite to purge the old Reddit secret from commit `17602a7`: **not run; owner decided it is not needed** (2026-11-03).
  Exact `git filter-repo` commands are in `01-security-hygiene.md`. Only do it if you accept breaking existing clones/forks.
- [ ] **Task 11** — Review `assets/loops/china_surfer_low.mp4` (18 MB, unknown provenance) and the SadTalker sample avatar
  (`full_body_1.png`, third-party demo image). Defaults proposed in Task 11: replace both with generated placeholders in the repo.
- [x] **Task 10/11** — Licence: owner delegated the choice → **MIT**, `LICENSE` added.
- [x] **Final** — Owner asked for the branch to be pushed (2026-11-03). Tagging and GitHub metadata remain with the owner.

## Decisions (answered)
- **Task 02** — `[tts]` and `[avatar]` extras cannot co-install under SadTalker's exact pins → **decided: two separate venvs**
  (documented in `docs/KNOWN_ISSUES.md` and the README). Loosening the pins needs a real GPU/Mac run to verify.
- **Task 02** — Machine is Apple Silicon → MPS-aware device handling; XTTS on MPS falls back to CPU with a warning.
- **Task 06** — Default search provider → **DuckDuckGo via `ddgs`** (free, no key). Google CSE stays as a deprecated provider.
- **Task 07** — `llm.max_retries: 3` means **3 retries after the first attempt** (up to 4 requests). Current behaviour kept.
- **Task 08** — Do not patch the SadTalker fork: the wrapper already works around the missing return value, the `sys.argv[0]` config
  path and the CWD-relative weights path (see `docs/KNOWN_ISSUES.md`). Revisit only if you want upstream-quality fixes.
- **Task 08** — Captions were skipped (the pipeline does not pass the script text to `compose()`); listed as a roadmap item.

## Still open
None. (Warning on a single `:free` model and the CI-badge repo URL were dismissed by the owner.)
