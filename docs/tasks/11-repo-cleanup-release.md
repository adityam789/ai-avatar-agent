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
