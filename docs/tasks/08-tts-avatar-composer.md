# 08 — TTS, avatar, composer cleanup

## Goal
Make the three heavy stages lazy, configurable, and robust.

## TTS (`stages/tts.py`)
- Currently instantiates XTTS v2 at import time (slow, requires model for any import) and hard-codes speaker "Ana Florence", `gpu=False`.
- Do: lazy-load inside a cached `get_tts()`; device from config (`auto` = cuda > mps > cpu; note XTTS on MPS may be flaky — fall back to cpu with a warning); speaker/language/optional `speaker_wav` (voice cloning reference) from config; write to run dir; return `Path`; verify the file exists and duration > 0.
- Switch dependency to `coqui-tts` (Task 02). Add a `FakeTTS` (writes a short silent wav via stdlib `wave`) for tests/offline.
- Note licence in docstring: XTTS v2 weights = Coqui Public Model License (non-commercial).

## Avatar (`stages/avatar.py`)
- Currently calls `models.sad_talker.inference.run(...)` which returns None, then picks newest mp4 by glob.
- Do: wrapper adds the submodule dir to `sys.path` cleanly, passes ABSOLUTE `checkpoint_dir`/`result_dir`, `still=True`, `preprocess='full'`, configurable `size` (256/512), `enhancer` (None/gfpgan), `pose_style`, `expression_scale`. Determine output by listing `result_dir` before/after (or unique per-run result_dir) — never `sorted(glob)[-1]`.
- If it requires editing the submodule (e.g. make `run()` return the result path, remove `sys.argv[0]`-based config path), do it in a branch of the fork, commit there, and bump the submodule pointer. Document in `docs/KNOWN_ISSUES.md`. Ask the owner before pushing to the fork.
- Validate: source image exists, audio exists, checkpoints present (clear message pointing to SadTalker `scripts/download_models.sh`).
- Add a `FakeAvatar` that renders a still image + audio into an mp4 via ffmpeg for tests/offline demos.

## Composer (`stages/compose.py`)
- Currently: ffmpeg `filter_complex` with scale+crop+vstack, `-shortest`, `-map 0:a?`, no codec/pixel-format flags.
- Do: build the command in a pure function `build_ffmpeg_cmd(...)` (unit-testable); use `scale=...:force_original_aspect_ratio=increase,crop=...` for BOTH tiles to avoid stretching the avatar; add `-c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p -c:a aac -movflags +faststart`; `-t` = audio duration (ffprobe) instead of relying on `-shortest` with an infinite loop; check `ffmpeg` exists with a friendly error; capture stderr and surface the tail on failure.
- Optional stretch: burned-in captions from the script using ffmpeg `subtitles`/`drawtext` with simple word timing (even splitting by duration is OK). Behind `captions.enabled`.

## Acceptance criteria
- `ai-avatar run "x" --offline` (fakes for LLM/TTS/avatar, real ffmpeg) produces a playable 1080x1920 mp4 on a laptop with no GPU.
- Unit test for `build_ffmpeg_cmd` snapshot.
