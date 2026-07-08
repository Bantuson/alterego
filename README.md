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
(~20 fps at 640px on a 4 GB machine, measured). Any app that accepts a
webcam — OBS, YouTube Live, Zoom, Meet — selects the virtual camera and
sees only the protected feed, which makes streams and even video calls
pseudonymous.

**Live inverts the safety model.** In post, a frame with no detected
face passes through and you review it before publishing. Live, that
frame would leak your real face to the audience, unreviewably. So live
mode FAILS CLOSED: lost landmarks pixelate the person region until the
face is re-acquired, and the voice thread outputs silence on any error —
never the raw microphone.

## Quickstart

Requires Python 3.10+, [uv](https://docs.astral.sh/uv/), and ffmpeg
(`winget install Gyan.FFmpeg`).

```powershell
uv sync

# 1. Create your alter ego (K saves it to alterego.json — treat that
#    file like a password and back it up):
uv run alterego preview                                  # audition random faces
uv run alterego design --jaw 0.8 --eyes-apart -0.5       # or design it
uv run alterego design --like reference.jpg              # or match proportions

# 2. Record (or copy a phone clip and `prep` it), then either:
uv run alterego ship take.mp4 --image street.jpg         # the whole pipeline
uv run alterego clip take_ship.mp4 --title "Your hook"   # branded 9:16 render

# 3. Or go live:
uv run alterego live --window
```

Run the tests with `uv run pytest`.

📖 **The full setup and usage manual — every prerequisite (OBS,
VB-Cable, Node), every command, every tuning flag, and the
troubleshooting table — is [docs/GUIDE.md](docs/GUIDE.md).** That file
is the source of truth for operating alterego.

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

## Docs

- **[docs/GUIDE.md](docs/GUIDE.md)** — the operator's manual: setup,
  social workflow, live workflow, troubleshooting. Source of truth.
- [docs/ROADMAP.md](docs/ROADMAP.md) — what shipped per phase and
  what's beyond v1.
- [docs/rebuild-guide.html](docs/rebuild-guide.html) — how this project
  was thought into existence, layer by layer, for anyone who wants to
  rebuild it (open in a browser).
