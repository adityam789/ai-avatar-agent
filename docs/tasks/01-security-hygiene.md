# 01 — Security & secrets hygiene

## Goal
Make the repo safe to publish publicly.

## Context
- `app/agents/research/test_research.py` has a hard-coded Reddit `client_id` and `client_secret`; it is in git history (commit 17602a7 and later).
- `.env` exists locally and is gitignored (keys: GOOGLE_API_KEY, GOOGLE_CSE_ID, OPEN_ROUTER_API_KEY, OPEN_ROUTER_REFERER, OPEN_ROUTER_TITLE, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT). Never read its values.

## Steps
1. Replace hard-coded creds in `test_research.py` with env-var reads (skip the test if unset). Later tasks will move it under `tests/`.
2. Create `.env.example` listing every variable name with empty values and a one-line comment each.
3. Extend `.gitignore`: `*.wav`, `*.mp4` (except an explicit `docs/assets/` demo), `models/**/checkpoints/`, `.env.*` (but not `.env.example`), `*.pth`, `*.safetensors`, `*.egg-info/`, `.pytest_cache/`, `.ruff_cache/`.
4. Run a secret scan on the working tree AND history (`gitleaks detect` or `trufflehog git file://.`; install via pip/brew if missing). Report findings in this file.
5. Write `SECURITY.md`-style note in README later (Task 10): how to configure keys.
6. History rewrite: DO NOT run. Write the exact `git filter-repo` commands in "Owner actions" below and wait for approval. Rotation is the real fix.

## Owner actions (Aditya, manual)
- [ ] Rotate the Reddit app secret (reddit.com/prefs/apps) — treat the committed one as burned.
- [ ] Rotate OpenRouter / Google keys if the repo was ever public or shared.
- [ ] Decide: rewrite history (clean, breaks existing clones/forks) vs. just rotate and move on.

## Findings (secret scan, 2026-11-03)
Tool: `gitleaks` (brew), run with `--redact`.
- Working tree (tracked + untracked-not-ignored, excluding the submodule): **no leaks**.
- Git history (`gitleaks git .`): **1 finding** — `generic-api-key` in `app/agents/research/test_research.py:15`, commit `17602a7` (the Reddit client secret). `.env` was never committed.
- Not scanned: the `models/sad_talker` submodule history (separate repo).

## Owner actions: history rewrite (NOT RUN — awaiting approval)
Rotation is the real fix. If you also want the secret gone from history (breaks existing clones/forks; requires force-push):
```bash
pip install git-filter-repo
git clone --no-local . ../ai-avatar-agent-rewrite && cd ../ai-avatar-agent-rewrite
# Replace the leaked literals with ***REMOVED*** everywhere in history
printf '%s\n' 'LITERAL_CLIENT_SECRET==>***REMOVED***' 'LITERAL_CLIENT_ID==>***REMOVED***' > ../replacements.txt
git filter-repo --replace-text ../replacements.txt
gitleaks git . --redact          # confirm clean
# then, only if you accept the consequences:
git remote add origin <url> && git push --force --all
```
(Fill the two literals from `git show 17602a7:app/agents/research/test_research.py`; do not commit `replacements.txt`.)

## Acceptance criteria
- `grep -rIn "client_secret\s*=\s*\"" .` returns nothing in tracked files.
- `.env.example` exists; `.env` is untracked.
- Secret scan of working tree is clean.

## Open questions
- History rewrite yes/no?
