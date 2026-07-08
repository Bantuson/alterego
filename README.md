# alterego

**A terminal-first content studio for camera-shy builders.**

Build in public without putting your real face on the internet. alterego
records you, then *geometrically* shifts your facial proportions — jaw,
eyes, nose, mouth — by a few seeded percent so you look like a consistent
"alter ego" while your movement, expressions, and speech stay perfectly
natural. Then it fixes your lighting and color like a studio, and cuts
the dead air like an editor. All from the command line.

No deep fakes, no cloud upload of your face, no GPU required. Pure
classical computer vision, built to run on a 4 GB laptop.

## The pipeline

```
record/prep ─► disguise ─► background ─► enhance ─► cut ─► voice ─► clip
(ffmpeg)       (MediaPipe   (segmentation (OpenCV    (silence (pitch  (Remotion
                + warp)      + composite)  grading)   +fillers) shift)  9:16 brand)
```

Or all of it in one command:

```powershell
uv run alterego ship take.mp4 --image street.jpg
uv run alterego clip take_ship.mp4 --title "Building a CV pipeline on 4GB of RAM"
```

## Live mode

The same identity, in real time — face warp, background, color grade,
and voice shift applied to your webcam and microphone as they happen
(~20 fps at 640px on a 4 GB machine, measured):

```powershell
uv sync --extra live
uv run alterego live --window              # rehearse in a preview window
uv run alterego live                       # -> virtual camera (install OBS once)
uv run alterego live --voice --audio-out "CABLE Input"   # + alter-ego mic
```

Any app that accepts a webcam — OBS, YouTube Live, Zoom, Meet — can
select the virtual camera, which makes live streaming and even video
calls pseudonymous.

**Live inverts the safety model.** In post, a frame with no detected
face passes through and you review it before publishing. Live, that
frame would leak your real face to the audience, unreviewably. So
live mode FAILS CLOSED: if landmarks drop, the person region is
pixelated (segmentation keeps working in conditions where landmark
detection dies — measured, not assumed) until the face is re-acquired.
The voice thread has the same rule: on any error it outputs silence,
never the raw microphone.

Every stage reads a video file and writes a new one. You can re-run any
stage alone, inspect the output between steps, and nothing is ever held
in memory except a single frame.

Because files are the interface, footage from ANY camera works — the
webcam recorder is just one way in. Phone footage shot outside in
daylight beats a webcam at night by more than any algorithm can:

```powershell
# copy the clip from your phone (USB cable -> This PC -> phone -> DCIM)
uv run alterego prep phone_clip.mp4     # phone codecs/VFR -> pipeline-friendly 720p
uv run alterego disguise phone_clip_prep.mp4
uv run alterego background phone_clip_prep_alterego.mp4 --image street.jpg
uv run alterego enhance ...             # grade AFTER background: a shared
uv run alterego cut ...                 # grade visually "glues" a composite
```

`background` with no `--image` simply blurs your real surroundings
(privacy, zero setup). With `--image`, it composites you onto any
backdrop — it is auto-blurred slightly so it reads as camera depth
of field rather than a green screen.

## Quickstart

Requires Python 3.10+, [uv](https://docs.astral.sh/uv/), and ffmpeg
(`winget install Gyan.FFmpeg`).

```powershell
uv sync

# 1. Find your camera and microphone names
uv run alterego devices

# 2. Choose your alter ego. Either audition random ones live
#    (N = new face, K = keep), or design one deliberately:
uv run alterego preview
uv run alterego design --jaw 0.8 --eyes-apart -0.5      # explicit knobs
uv run alterego design --like reference.jpg              # match a face's proportions
# The identity (8 face knobs + a voice seed) persists in alterego.json —
# gitignored, because whoever holds it can reproduce or invert your disguise.
# --like nudges your PROPORTIONS toward the reference within a naturalness
# budget; it cannot make you look like that person. Prefer AI-generated
# reference portraits over photos of real people.

# 3. Record camera + screen (press Enter to stop)
uv run alterego record --camera "Your Camera Name" --mic "Your Mic Name" --screen

# 4. Apply your saved alter ego (same seed every video = consistent identity)
uv run alterego disguise recordings/take_camera.mp4

# 5. Studio lighting and color
uv run alterego enhance recordings/take_camera_alterego.mp4

# 6. Cut the silent gaps — add --fillers to also cut "um"/"uh"
#    (filler removal needs: uv sync --extra speech)
uv run alterego cut recordings/take_camera_alterego_graded.mp4 --fillers
```

Run the tests with `uv run pytest`.

## How the disguise works (the interesting part)

Face identity — to both humans and recognition models — lives largely in
the *ratios* between features: how wide the jaw is relative to the face,
how far apart the eyes sit, how long the nose is. `disguise.py`:

1. Detects **468 face landmarks** per frame with MediaPipe Face Mesh.
2. Derives an **alter-ego profile** from a random seed: eight numbers
   saying how much to push each feature (jaw width, eye spacing, ...).
   Same seed → same face, forever. Treat your seed like a password.
3. Builds a **Gaussian displacement field** — think Photoshop's Liquify:
   each landmark drags nearby pixels with a smooth falloff.
4. Applies it with `cv2.remap`. Pixels only *move*; none are invented.
   That's why skin texture, lip-sync, and expressions survive intact.

Because every change is capped at a few percent of face width, the
result doesn't look edited — you just look like a relative of yourself.

⚠️ **Honest limitations:**
- This raises the cost of recognizing you; it is not cryptographic
  anonymity. The `voice` stage shifts your pitch (seeded, consistent —
  same rule as the face), but *what you say* — names, places, your
  story — identifies you more than any biometric.
- The disguise needs to SEE your face. On dark footage, landmark
  detection fails and frames pass through with your real face —
  `disguise` now reports its coverage and warns loudly below 90%.
  Light your face, or record outside. `enhance --night` exists as a
  salvage mode for watchability, but it cannot restore detail the
  sensor never captured.

## Design notes for a 4 GB machine

- **Stream, never load.** One frame in memory at a time (`video_io.py`).
- **Record cheap, encode later.** `x264 ultrafast` while recording so
  frames aren't dropped; nicer compression happens offline in post.
- **Compute small, upscale.** The displacement field is computed at ¼
  resolution and interpolated up — smooth fields lose nothing.
- **Let ffmpeg do ffmpeg things.** Audio, containers, and cutting run
  in native code; Python only does the vision.

## When you outgrow this machine (free tiers)

| Need | Free option |
|------|-------------|
| GPU for heavier models (voice conversion, upscaling) | Google Colab free tier; Kaggle Notebooks (~30 GPU h/week) |
| Rendering Remotion social clips in the cloud | GitHub Actions (2,000 min/month free) |
| Hosting a demo | Hugging Face Spaces (free CPU) |

## Roadmap

This weekend build is Phase 1. Filler-word removal, Remotion social
clips, and background replacement are next — see
[docs/ROADMAP.md](docs/ROADMAP.md).
