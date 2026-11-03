# Known issues

## Dependency pins are intentionally old (SadTalker)
SadTalker's `requirements.txt` pins `numpy==1.23.4`, `scipy==1.10.1`, `librosa==0.9.2`, and the project targets
`torch==2.1.2` / `torchvision==0.16.2` / `torchaudio==2.1.2`. The `[avatar]` extra in `pyproject.toml` mirrors these.
They are **not** upgraded blindly. An upgrade would need: re-testing SadTalker on a newer torch/librosa (its
`src/utils/audio.py` already passes keyword arguments to `librosa.filters.mel`, so that call is likely fine),
and a patch for numpy >= 1.24, which removed the `np.float` / `np.int` aliases still used in
`models/sad_talker/src/face3d/util/my_awing_arch.py` and `.../arcface_torch/eval_ijbc.py` (a change inside the submodule,
which this effort does not make). The face-alignment/GFPGAN stack would also need re-checking.
Python 3.10 is the supported interpreter (pinned by `.python-version`; CI will use it, Task 09).

## `[tts]` and `[avatar]` extras cannot be installed into one environment (verified 2026-11-03)
`pip install --dry-run -e ".[tts]"` and `-e ".[avatar]"` each resolve on their own (Python 3.10, macOS arm64), but
`-e ".[tts,avatar]"` does not:

| `coqui-tts` release | needs | clashes with `[avatar]` pin |
|---|---|---|
| 0.28.0 (latest) | numpy>=1.26, scipy>=1.13, librosa>=0.11, torch>=2.2, transformers>=4.57 | all of them |
| 0.24.3 | numpy>=1.25.2, scipy>=1.11.2, librosa>=0.10.1, transformers>=4.43 | numpy, scipy, librosa |
| 0.22.1-0.23.1 (oldest forks) | pip reports no resolution together with `numpy==1.23.4`, `librosa==0.9.2`, `scipy==1.10.1`, `torch==2.1.2` (exact constraint not itemised; sdist-only, not inspected) | at least one of numpy/librosa/scipy |

Options (owner decision, see `docs/tasks/OWNER_QUESTIONS.md`):
1. **Two environments** (safe default): run TTS in one venv and the avatar stage in another, handing over the wav file.
   Task 08 keeps the stages decoupled through files, so this works without code changes.
2. **Relax the SadTalker pins** to the combination reported by `pip list` in the author's local `.venv` on 2026-11-03
   (`torch 2.1.2`, `numpy 1.22.0`, `scipy 1.11.4`, `librosa 0.10.0`, legacy `TTS 0.22.0`; note this is not the
   `numpy==1.23.4` pin in `[avatar]`) and verify on real hardware.
   Not done here because it cannot be verified without GPU/model downloads.

## External services
- **Google Custom Search JSON API**: closed to new customers, discontinued 2027-01-01.
- **Reddit Data API**: requires approval (Responsible Builder Policy); new requests reportedly closed 2026-10-31.
- **OpenRouter `:free` models** rotate and throttle without notice; the LLM layer needs fallbacks.

## Licences
- XTTS v2 weights: Coqui Public Model License (non-commercial).
- SadTalker code is Apache-2.0; pretrained weights and third-party components have their own terms.
