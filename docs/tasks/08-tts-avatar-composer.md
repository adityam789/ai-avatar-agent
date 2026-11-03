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

## Results (2026-11-03)

**Done**
- `stages/tts.py`: lazy, `lru_cache`d `get_tts(device)` (importing the module pulls in neither torch nor `TTS`; tested in a subprocess).
  Device logic is two small functions: pure `resolve_device(requested, cuda=, mps=)` (auto = cuda > mps > cpu; an explicitly requested
  but missing accelerator raises `TTSError`) and `xtts_device(...)`, which turns MPS into cpu with a logged warning. Speaker, language
  and optional `tts.speaker_wav` (voice cloning, replaces `speaker`) come from config. Output is verified (exists, readable by stdlib
  `wave`, duration > 0); backend errors become scrubbed `TTSError`s; missing package gives the `pip install -e '.[tts]'` hint.
- `stages/fakes.py` (new): `FakeTTS` (silent wav, 2.5 words/s, min 0.5 s) and `FakeAvatar` (still image + audio -> mp4 via real ffmpeg,
  named like SadTalker's `<timestamp>.mp4`). Both mimic the real backend's call shape, so the real wrapper code (voice options,
  output detection) runs in offline mode too. `generate_audio` / `generate_avatar` pick them when `cfg.offline`.
- `stages/avatar.py`: passes absolute `checkpoint_dir`/`result_dir`/audio/image and `size`, `enhancer` (`none` -> `None`), `pose_style`,
  `expression_scale`, `still`, `preprocess` from `cfg.avatar`. Validates image, audio, submodule checkout, the checkpoint files that
  the chosen size/preprocess need (and the GFPGAN weights when enhancer is gfpgan) with messages pointing to `download_models.sh`.
  Output = `.mp4` new or rewritten in the (per-run) result dir (before/after mtime snapshot); none -> error mentioning face detection.
  `_sadtalker_context` is unchanged except for an opt-in `chdir=` (used only for gfpgan). Dropped the unused `bfm_folder` argument.
- `stages/compose.py`: pure `build_ffmpeg_cmd(...)`; both tiles `fps=25,scale=...:force_original_aspect_ratio=increase,crop`; libx264 /
  `cfg.video.preset` / `crf` / yuv420p / aac / `+faststart`; `-t` = ffprobe duration of the avatar video (so the endless background loop
  is cut); even avatar height; friendly error when ffmpeg/ffprobe are missing; stderr tail (12 lines) in `ComposeError`.
- `checks.py`: with `cfg.offline` the SadTalker-checkpoint and API-key checks are reported but not required (ffmpeg, ffprobe, avatar
  image, loop still are). `tests/test_cli.py` needed no change.

**Verified** (`<venv>/bin/pytest`: 136 passed, 1 skipped = SadTalker-submodule test, empty in the worktree)
- Real ffmpeg, no mocks: `tests/test_compose_e2e.py` composes generated avatar+loop (loop shorter than audio) into 1080x1920 h264 / yuv420p /
  aac with duration == audio; runs `FakeTTS -> FakeAvatar -> compose` in ~1 s; runs `pipeline.run(..., script_file=...)` offline.
- `ai-avatar run demo --offline --script-file s.txt --avatar-image img.png` (real loop asset, 9.2 s of audio): 4.6 s wall, valid 1080x1920 mp4.
  An 18 s fake narration composes in ~7 s on this M-series laptop.
- `AI_AVATAR_ROOT=<main checkout> pytest tests/test_avatar_context.py`: the "SadTalker `src` wins over repo `src`" test passes against the
  populated submodule.

**Could NOT verify** (no torch, no weights, no network here)
- A real XTTS or SadTalker run. `TTS(MODEL_NAME).to(device)`, `tts_to_file(speaker_wav=...)`, and the licence prompt behaviour
  (`COQUI_TOS_AGREED=1` for non-interactive first download) follow the coqui-tts docs but are unexercised. The wav check reads PCM with `wave` and
  falls back to ffprobe for float / extensible wavs (see review round 1).
- SadTalker quirks found by reading `inference.py`: `run()` returns `None` and writes `<result_dir>/<YYYY_mm_dd_HH.MM.SS>.mp4`
  (second resolution, hence the per-run dir); it silently returns without a file when no face is found; it picks only cuda or cpu (no MPS
  support, so on Apple silicon the avatar renders on cpu); the model config dir is derived from `sys.argv[0]` as
  `<root>/models/sad_talker/src/config`, so `paths.sadtalker_dir` must stay `models/sad_talker`; the GFPGAN enhancer reads
  `./gfpgan/weights` relative to the CWD (and silently downloads if missing), hence the opt-in chdir plus an up-front weights check.
- XTTS on MPS: handled by falling back to cpu (not testable here).

**Deviations**
- Captions (optional stretch) were skipped: `compose()` has no access to the script text and `pipeline.py` is not mine to change;
  `captions.enabled` is documented as ignored in the compose docstring.
- Centre-crop of the avatar tile can cut off a face in tall full-body videos; a top-anchored crop may suit those images better.
- New test helper `tests/ffmpeg_media.py` (tiny generated media + ffprobe wrapper).

**Open questions for the owner**
- Should the submodule fork get a small patch (`run()` returns the output path; config dir not derived from `sys.argv[0]`; weights paths
  absolute)? The wrapper works around all three, so it is optional.
- Add captions later by passing the script to `compose()` from the pipeline adapter?

### Review round 1 fixes
- `tts.generate_audio` deletes `output_path` before synthesis and again before every verification error, so a stale file can no longer
  pass the "was written" check and a rejected (empty / garbage) wav is not left behind.
- `tts.wav_duration` falls back to `compose.probe_duration` (ffprobe) when stdlib `wave` rejects float32 / WAVE_FORMAT_EXTENSIBLE wavs; a
  truly unreadable file (or no ffprobe) is still a `TTSError`. NaN / inf / non-positive durations are rejected.
- `get_tts` error mentions the licence (CPML, non-commercial) and `COQUI_TOS_AGREED=1` / running once interactively.
- `cli._dry_run`: SadTalker checkpoints are required only when the avatar stage is planned; the avatar image only for avatar; the background
  loop only for compose (offline still needs those files). Tests in `tests/test_cli.py`.
- `compose`: ffmpeg and ffprobe stderr tails go through `redact.scrub`; a failing ffprobe reports its stderr; NaN / inf / <= 0 durations are
  errors before ffmpeg runs.
- Stale comments in `config.py` / `config/default.yaml` (device handling) updated; ruff (E,F,I,W,SIM,ISC at 120) is clean in this task's files.
  Note: without a ruff config, `ffmpeg_media` sorts as third-party; if Task 09 declares tests as first-party, re-sort those imports.

**Open items**: the default `avatar.image` lives only in the submodule, so a fresh clone without it fails the "avatar image" check (Task 11 ships a
placeholder avatar). Pre-existing >120-char lines in `cli.py` / `tests/test_cli.py` belong to other tasks.

**KNOWN_ISSUES material** (SadTalker quirks, for Task 10): no MPS support (cuda or cpu only, so Apple silicon renders on cpu); the model
config dir is derived from `sys.argv[0]` (`<root>/models/sad_talker/src/config`); no file is written, and no error raised, when no face is
detected; the GFPGAN enhancer reads weights from `./gfpgan/weights` relative to the CWD (and downloads silently if missing); `inference.run`
returns `None` and writes `<result_dir>/<YYYY_mm_dd_HH.MM.SS>.mp4`. XTTS v2 is unreliable on MPS, so TTS also runs on cpu there.
