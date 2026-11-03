# Task Index

Work in order. Each file has: Goal, Context, Steps, Acceptance criteria, Open questions.
Mark a task done by checking its box here and committing.

- [x] 01 — Security & secrets hygiene (`01-security-hygiene.md`)
- [x] 02 — Packaging, dependencies, Python version (`02-packaging-deps.md`)
- [x] 03 — Restructure into a proper package + config (`03-package-and-config.md`)
- [x] 04 — Orchestrator: real pipeline, run dirs, resumability (`04-orchestrator.md`)
- [x] 05 — CLI and `__main__` (`05-cli.md`)
- [x] 06 — Research agent robustness + pluggable search (`06-research-robustness.md`)
- [x] 07 — LLM client + script agent (`07-llm-and-script.md`)
- [ ] 08 — TTS, avatar, composer cleanup (`08-tts-avatar-composer.md`)
- [ ] 09 — Tests, lint, CI (`09-tests-ci.md`)
- [ ] 10 — Docs: README, architecture, status (`10-docs-readme.md`)
- [ ] 11 — Repo cleanup & release (`11-repo-cleanup-release.md`)
- [ ] 12 — (Optional stretch) FastAPI service (`12-optional-api.md`)

## Dependencies between tasks
01 -> everything (do first). 02 -> 03 -> 04 -> 05. 06/07/08 can follow 03 in any order. 09 after 06-08. 10 after 05 and 09. 11 last.

## Ground rules
See `CLAUDE.md` at repo root.
