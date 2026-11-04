# 11 — Repo cleanup & release

## Goal
Small repo, clean history going forward, tagged release.

## Context
Tracked today: `output.wav` (305 KB, repo root), `assets/loops/china_surfer_low.mp4` (18 MB). Ignored: `outputs/`, `gfpgan/`, `.venv/`. Submodule: `models/sad_talker` -> fork `adityam789/SadTalker`.

## Steps
1. `git rm --cached output.wav` (+ delete only after owner OK). Any demo media for the README goes to `docs/assets/` and must be small (<10 MB; compress with ffmpeg `-crf 28`, 540p, or produce a GIF).
2. Background loop (18 MB): options — keep (acceptable), move to Git LFS, or replace with a tiny generated/synthetic loop (e.g. ffmpeg `testsrc` / `gradients`) and document "bring your own loop". ALSO consider copyright: the gameplay/surfer clip's provenance is unknown. Recommend a placeholder + doc. Ask owner.
3. Add `.gitattributes` (LF endings, mark binaries).
4. Submodule: confirm `.gitmodules` URL; document `git clone --recurse-submodules` and the checkpoint download step. Note the fork's divergence from upstream (what changed and why) in `docs/KNOWN_ISSUES.md` or the fork's README.
5. Sample assets: the SadTalker examples used as default avatar (`full_body_1.png`) are third-party demo images; document or replace with a clearly-licensed/own/generated avatar placeholder.
6. Final checklist: fresh clone in a temp dir -> follow README -> offline demo succeeds; secrets scan clean; `pytest` + `ruff` pass; CI file present.
7. Version `0.1.0` in `pyproject.toml`; `CHANGELOG.md`; propose `git tag v0.1.0` (owner pushes).
8. Prepare (don't run) the commands for owner: `git push`, set GitHub repo description/topics (`ai`, `talking-head`, `tts`, `llm`, `ffmpeg`, `python`), pin repo, optional "archived" setting once done.

## Acceptance criteria
- `git ls-files | xargs du -ch | tail -1` reasonably small (target < 5 MB excluding submodule).
- No generated outputs tracked.

## Open questions
- Keep/replace the loop video and sample avatar? Choose license (MIT?).

## Results (2026-11-03)
- Tracked size (excluding the submodule gitlink): **1.4 MB** (was 19 MB). No generated outputs tracked (`outputs/`, `*.wav`, `*.mp4` ignored; `docs/assets/` and the placeholder loop are explicit exceptions).
- `output.wav` and `assets/loops/china_surfer_low.mp4` were **untracked with `git rm --cached` — the files are still on disk** (nothing deleted). The 18 MB clip remains in git *history*
  (shrinking history needs a rewrite — owner decision, not done). Its provenance is unknown, so the repo no longer ships it; point to it locally with `--loop` or `background.loop`.
- Defaults now use generated placeholders: `assets/avatars/placeholder.png` (drawn with ffmpeg) and `assets/loops/placeholder_loop.mp4` (6 s gradient, 24 KB). The SadTalker sample image
  (`full_body_1.png`, third-party) is no longer a default. A real run needs a real face image (`--avatar-image`); the placeholder is only enough for the offline fakes.
- `.gitattributes` (LF, binaries), `CHANGELOG.md`, version `0.1.0` (already in `pyproject.toml`), ruff pinned to 0.8.6 in `[dev]` to match pre-commit.
- Submodule: `.gitmodules` -> `https://github.com/adityam789/SadTalker.git`; the pinned commit `398f403` ("Modified inference.py for ai-avatar-agent compatibility") is on the fork's `origin/main`
  (local remote-tracking ref), so a fresh `--recurse-submodules` clone can fetch it. Fork divergence is documented in `docs/KNOWN_ISSUES.md`.
- Owner commands (NOT run): see the final report / `docs/tasks/OWNER_QUESTIONS.md`.
