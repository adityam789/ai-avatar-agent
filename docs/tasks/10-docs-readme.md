# 10 — Docs: README, architecture, status

## Goal
A README that sells the project to a recruiter in 60 seconds and lets an engineer run it in 5 minutes.

## README structure
1. Title + one-line pitch + badges (CI, Python 3.10, license).
2. **Demo**: short GIF/MP4 thumbnail at top (<10 MB, stored in `docs/assets/`; see Task 11). Describe what the viewer is seeing.
3. **Project status**: honest note — "Feature-complete prototype, now archived/maintenance-only. Reddit and Google CSE integrations are affected by upstream API changes (details in docs/KNOWN_ISSUES.md); offline demo mode works with no keys."
4. **How it works**: Mermaid flowchart of the pipeline + 1 paragraph per stage.
5. **Quickstart**: prerequisites (Python 3.10, ffmpeg), install, `ai-avatar doctor`, offline demo command, real run command, config overview, `.env.example` explanation.
6. **Configuration** table (key, default, meaning).
7. **Project layout** tree.
8. **Design decisions & tradeoffs** (short bullets): staged pipeline w/ resumable artifacts, fail-soft collectors, pluggable providers, fakes for testing heavy models, lazy imports.
9. **Limitations & roadmap** (what would be upgraded next: newer talking-head models, streaming TTS, captions, new search/Reddit alternatives).
10. **Licensing & credits**: SadTalker (Apache-2.0 code; check weights terms), XTTS v2 (CPML non-commercial), GFPGAN, OpenRouter models' own terms. Add an AI-generated/synthetic-media disclosure note and a responsible-use note (voice/face synthesis; only use images/voices you have rights to).
11. LICENSE file: ask owner which (MIT recommended) — create after confirmation; list in open questions.

## Other docs
- `docs/architecture.md`: component diagram (Mermaid), data flow, run-directory layout, error-handling model, extension points (how to add a collector / provider / stage).
- `docs/KNOWN_ISSUES.md`: Google CSE shutdown (2027-01-01), Reddit approval, OpenRouter free-model churn, old torch/transformers pins, XTTS licence, SadTalker quirks, MPS/CPU performance notes.
- `docs/RESUME_BULLETS.md`: 3–5 resume bullet options (quantified where honest: e.g. stages, test coverage, CI) + a 30-second interview talk track + "what I'd do differently". Keep claims accurate to what exists in the repo.
- `CONTRIBUTING.md` (short) — optional.
- Docstrings on public functions; module docstrings fixed (several are stale).

## Acceptance criteria
- A reader who has never seen the repo can run the offline demo from README commands alone (verify by following them literally).
- All README links/paths resolve.
