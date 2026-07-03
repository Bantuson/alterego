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
record ──► disguise ──► enhance ──► cut ──► publish
(ffmpeg)   (MediaPipe    (OpenCV     (ffmpeg
            + warp)       grading)    silence cut)
```

Every stage reads a video file and writes a new one. You can re-run any
stage alone, inspect the output between steps, and nothing is ever held
in memory except a single frame.

## Quickstart

Requires Python 3.10+, [uv](https://docs.astral.sh/uv/), and ffmpeg
(`winget install Gyan.FFmpeg`).

```powershell
uv sync

# 1. Find your camera and microphone names
uv run alterego devices

# 2. Audition alter egos live — press N to try new seeds, note the one you like
uv run alterego preview

# 3. Record camera + screen (press Enter to stop)
uv run alterego record --camera "Your Camera Name" --mic "Your Mic Name" --screen

# 4. Apply your alter ego (SAME seed every video = consistent identity)
uv run alterego disguise recordings/take_camera.mp4 --seed 1337

# 5. Studio lighting and color
uv run alterego enhance recordings/take_camera_alterego.mp4

# 6. Cut the silent gaps
uv run alterego cut recordings/take_camera_alterego_graded.mp4
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

⚠️ **Honest limitation:** this raises the cost of recognizing you; it is
not cryptographic anonymity. Voice, environment, and what you say still
identify you. Phase 2 covers voice and background.

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
