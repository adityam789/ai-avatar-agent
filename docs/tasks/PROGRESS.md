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
| 08 TTS / avatar / compose | pending | - | |
| 09 Tests & CI | pending | - | |
| 10 Docs | pending | - | |
| 11 Cleanup & release | pending | - | |
| 12 Optional API | pending | - | |
