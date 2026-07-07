# Roadmap

Phase 1 (this weekend) shipped the core pipeline:
record → disguise → enhance → cut. Everything below builds on those
same "one file in, one file out" stages, so nothing here requires
rewriting what exists.

## Phase 1.5 — Filler-word removal ✅ SHIPPED

`cut --fillers` transcribes with faster-whisper (`tiny`, int8, fits
4 GB RAM), finds filler-word time ranges, and merges them with the
silence cuts. Unambiguous fillers (um/uh/erm/...) are cut by default;
context-dependent words are opt-in: `--also-cut like basically`.
Install once with `uv sync --extra speech`.

## Phase 2 — Environment augmentation (background replacement) ✅ SHIPPED

`alterego background` blurs your real room (default) or composites
you onto any backdrop image via MediaPipe selfie segmentation.
`alterego prep` normalizes phone footage (HEVC/variable frame rate →
H.264/30fps/720p) so any camera can feed the pipeline.

Color harmonization (`--harmonize`, Reinhard transfer toward the
backdrop's palette) and looping video plates also shipped.

## Phase 3 — Voice privacy ✅ SHIPPED

`alterego voice` pitch-shifts by a factor derived from your identity
seed (salted, so voice and face are independent draws; the ~1.0
"does nothing" zone is designed out). Uses ffmpeg's rubberband when
available, asetrate+atempo fallback otherwise. Verified by FFT.

Still open: RVC-style voice *conversion* on Colab free GPU for
higher-grade anonymity than a pitch shift.

## Phase 4 — Remotion social clips ✅ SHIPPED

`alterego clip take.mp4 --title "..."` renders a branded 9:16 clip:
dark launch-page look, hook title, rounded video card, word-timed
TikTok captions (whisper timestamps → @remotion/captions), handle +
progress bar. Design lives in `remotion/src/` (React); data decisions
live in `alterego/clips.py` (Python); they meet at a props JSON.
Renders with `--concurrency=1` to respect 4 GB of RAM.

Still open: render on GitHub Actions (2,000 free min/month) when the
machine is the bottleneck; a custom Claude Code brand skill.

## Phase 5 — One-command publish pipeline ✅ SHIPPED

`alterego ship take.mp4 [--image street.jpg]` = disguise → background
→ enhance → cut+fillers → voice, then `alterego clip` for the branded
render. Stage order is deliberate: detection sees raw pixels, grading
glues the composite, whisper hears the natural voice.

## Phase 6 — Live mode ✅ SHIPPED

`alterego live`: real-time disguise + background + tone grade to a
virtual camera (pyvirtualcam / OBS driver), with `--voice` running a
two-tap delay-line pitch shifter on the mic. Fail-closed by design:
lost landmarks pixelate the person; a voice error outputs silence.
Profiled 4.5 → 20 fps by fixing the glue, not the models (feather at
quarter res, cv2.blendLinear, threaded camera reads).

## Beyond v1

- RVC voice conversion (Colab) · GitHub Actions clip rendering ·
  brand skill · thumbnails · direct platform upload · GPU upgrade
  path (same code, 1080p30).
