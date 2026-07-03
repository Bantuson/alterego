# Roadmap

Phase 1 (this weekend) shipped the core pipeline:
record → disguise → enhance → cut. Everything below builds on those
same "one file in, one file out" stages, so nothing here requires
rewriting what exists.

## Phase 1.5 — Filler-word removal (next weekend, ~half day)

`cuts.py` already knows how to remove arbitrary time ranges. Fillers
("um", "uh", "like", "so yeah") just need *word-level timestamps*:

1. `uv sync --extra speech` (adds `faster-whisper`; the `tiny` model is
   ~75 MB and runs in <1 GB RAM with int8 quantization — fits the 4 GB
   machine).
2. New module `fillers.py`: transcribe with `word_timestamps=True`,
   collect the time ranges of words in a FILLERS set.
3. Feed those ranges into the existing `keep_segments` → `cut_video`
   path, merged with the silence ranges.

## Phase 2 — Environment augmentation (background replacement) ✅ SHIPPED

`alterego background` blurs your real room (default) or composites
you onto any backdrop image via MediaPipe selfie segmentation.
`alterego prep` normalizes phone footage (HEVC/variable frame rate →
H.264/30fps/720p) so any camera can feed the pipeline.

Still open in this phase:
- Color harmonization: automatically match subject/backdrop tones
  (currently approximated by running `enhance` after `background`).
- Video backdrops (a looping street plate instead of a still).

## Phase 3 — Voice privacy

The disguise protects your face; your voice is still you. Options in
increasing quality/cost order:

- Pitch/formant shift with ffmpeg's `rubberband` or `asetrate` chains
  (local, free, robotic if pushed hard).
- RVC-style voice conversion on Google Colab free GPU (great quality;
  batch process the audio track there, remux locally).

## Phase 4 — Remotion social clips

Turn polished takes into branded social posts (Node/React is already
installed):

- A Remotion project with brand tokens (colors, fonts, lower thirds,
  captions, progress bar) — the "VC-funded tech bro" skin.
- A Python `clips.py` that emits a JSON edit decision list (which
  segments, which captions) that the Remotion composition consumes.
- Render locally for short clips, or on GitHub Actions (2,000 free
  min/month) when the machine is the bottleneck.
- Add a custom Claude Code skill encoding your brand rules (hook in
  first 2 s, captions always on, 9:16 crop, end-card CTA) so every
  edit follows the same playbook.

## Phase 5 — One-command publish pipeline

`alterego ship take.mp4` = disguise → enhance → cut → fillers →
captions → Remotion render → thumbnail. A single command from raw
take to postable clip.
