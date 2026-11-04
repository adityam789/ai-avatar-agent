# Progress

| Task | Status | Commit | Notes |
|------|--------|--------|-------|
| 01 Security hygiene | done | 352b535 | gitleaks: tree clean, history 1 known finding (rotate; rewrite not run). Review: no blockers, 3 nits fixed |
| 02 Packaging & deps | done | 297f35b | .[dev] installs in ~13s, pytest ok. PARTIAL: .[tts,avatar] cannot co-resolve (documented, owner question). Review: no blockers |
| 03 Package & config | done | 16e502c | src/ai_avatar layout, pydantic Config, SadTalker CWD/shadowing handled w/o submodule edits. Review: round1 FAIL (src namespace shadowing) -> fixed, round2 PASS |
| 04 Orchestrator | done | 11fe32c | pipeline.run/dry_run, resume, overrides, typed errors, redact.scrub. 45 tests. Review: 3 rounds (R1 FAIL, R2 4 defects incl. secret leak, R3 PASS + 4 minor fixed unreviewed) |
| 05 CLI | done | e581633 | run/research/script/doctor, --dry-run via shared planner. 90 tests. Review: 3 rounds, each found real defects; final fix (single planner) not re-reviewed (cap) |
| 06 Research robustness | done | 136151e (merge of b5ddadc, e181491, e15695a) | Fail-soft collectors w/ wall-clock timeouts, DDG default, disk cache, offline fixtures, JSON salvage. Review: R1 FAIL (timeouts, JSON salvage) -> R2 PASS + 4 residual fixes |
| 07 LLM + script | done | 85e55b2 (merge) + 5bf8812 + 54f9ba8 | Retry/backoff/fallback client, FakeLLM, word-budgeted sanitized script. Review: R1 FAIL (8 defects) -> R2 (5 more) -> R3 PASS |
| 08 TTS / avatar / compose | done | merge of 65cd7ae + 40db6b5, plus range fix | Lazy XTTS + device logic, SadTalker wrapper (no submodule edits), ffmpeg composer, FakeTTS/FakeAvatar. Offline e2e `ai-avatar run OpenAI --offline` verified (1080x1920, 8.7 s). Review: R1 no blockers/7 defects -> R2 PASS. Captions skipped. Real XTTS/SadTalker runs NOT verified |
| 09 Tests & CI | done | 3ed5672 | ruff config + format, conftest network guard, CI (3.10/3.11), pre-commit, Makefile; 401 tests ~8 s, 97% branch cov; py3.11 verified locally. CI NOT run on GitHub. Review: PASS (fresh-clone w/ empty submodule verified) |
| 10 Docs | done | dfd1b90 | README, architecture, KNOWN_ISSUES, RESUME_BULLETS, CONTRIBUTING. LICENSE not created (owner). Doc fact-check review: see below |
| 11 Cleanup & release | done | 89e3dcc | Tracked size 19 MB -> 1.4 MB (files kept on disk, 18 MB clip still in history), generated placeholders as defaults, CHANGELOG, .gitattributes. Tag/push commands for owner |
| 12 Optional API | done | see git log (feat: optional FastAPI) | `ai-avatar serve`, jobs API, 12 tests, verified over real HTTP. NO independent review (optional stretch, budget) |
