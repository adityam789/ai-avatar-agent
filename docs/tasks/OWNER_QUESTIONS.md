# Owner questions & manual actions

Decisions and actions only Aditya can take. Each item notes the default chosen so work could continue.

## Manual actions
- [ ] **Task 01** — Rotate the Reddit app secret (reddit.com/prefs/apps); the committed one (commit `17602a7`) is burned.
- [ ] **Task 01** — Rotate OpenRouter / Google keys if the repo was ever public or shared.

## Decisions
- **Task 01** — Rewrite history to purge the leaked Reddit secret? Default: NO (rotate and move on). Commands are in `01-security-hygiene.md`.
- **Task 02** — `[tts]` and `[avatar]` extras conflict under SadTalker's exact pins (see `docs/KNOWN_ISSUES.md`). Default: document
  two separate venvs. Alternative: relax pins to your working `.venv` combo (torch 2.1.2, numpy 1.22, scipy 1.11.4, librosa 0.10.0,
  legacy `TTS 0.22.0`) after testing on your Mac. Which do you prefer?
- **Task 02** — Machine is Apple Silicon: confirm you want MPS-first device handling (Task 08 falls back to CPU for XTTS).
