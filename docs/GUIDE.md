# The alterego operator's guide

The source of truth for setting up and running everything — the
social (post-processing) pipeline and live mode. If this file and
another doc ever disagree, this file wins; fix the other one.

Contents:
1. [Setup from a clean machine](#1-setup-from-a-clean-machine)
2. [Your identity (do this once)](#2-your-identity-do-this-once)
3. [The social workflow: raw take → posted clip](#3-the-social-workflow)
4. [The live workflow: streams and calls](#4-the-live-workflow)
5. [Troubleshooting](#5-troubleshooting)
6. [Command reference](#6-command-reference)

---

## 1. Setup from a clean machine

### Core (required for everything)

| Tool | Install | Why |
|------|---------|-----|
| Python 3.10+ | [python.org](https://python.org) | the pipeline |
| uv | `winget install astral-sh.uv` | package manager (never use pip here) |
| ffmpeg | `winget install Gyan.FFmpeg` | recording, cutting, audio (restart the terminal after) |

```powershell
git clone https://github.com/Bantuson/alterego
cd alterego
uv sync                      # core: record, disguise, background, enhance, cut, voice
```

### Optional extras — install only what you use

```powershell
uv sync --extra speech       # filler-word removal + clip captions (~75 MB model on first use)
uv sync --extra live         # live mode (virtual camera + live mic)
```

### For `clip` (branded social renders) — Node side

| Tool | Install | Why |
|------|---------|-----|
| Node.js 20+ | [nodejs.org](https://nodejs.org) | Remotion runs on Node |

```powershell
cd remotion
npm install                  # once; ~400 MB of node_modules
npx remotion browser ensure  # downloads the render browser (~113 MB) once
cd ..
```

> Flaky connection? If the browser download keeps dying, fetch the zip
> resumably and place it manually — see [Troubleshooting](#5-troubleshooting).

### For `live` streaming — OBS (one-time)

The virtual camera is a *driver* that ships with OBS Studio:

1. Install OBS: `winget install OBSProject.OBSStudio`
2. Open OBS once, click **Start Virtual Camera**, then stop it and close
   OBS (this registers the driver).
3. `uv run alterego live` will now find the device. Without OBS, live
   mode still works in a preview window (`--window`).

### For live *voice* — VB-Audio Cable (one-time)

To make apps hear your shifted voice as "the microphone":

1. Download VB-CABLE from [vb-audio.com/Cable](https://vb-audio.com/Cable/)
   (free), run the installer, reboot.
2. This adds two devices: **CABLE Input** (you write into it) and
   **CABLE Output** (apps read from it).
3. Find exact names: `uv run alterego live --list-audio`

---

## 2. Your identity (do this once)

Your alter ego = **8 face knobs + 1 voice seed**, stored in
`alterego.json` in the project folder. It is gitignored like a
password: whoever holds it can reproduce — or invert — your disguise.
**Back it up somewhere private** (password manager note is perfect);
if you lose it, your alter ego's face is gone forever.

Three ways to create it:

```powershell
# A. Audition random faces (N = next face, K = keep, Q = quit)
uv run alterego preview

# B. Design it deliberately (all knobs -1..1; live preview, K to keep)
uv run alterego design --jaw 0.8 --eyes-apart -0.5 --lips 0.3
uv run alterego design --tweak --nose-length 0.4       # adjust saved identity
uv run alterego design --jaw 0.5 --save                # skip preview, save now

# C. Match a reference face's proportions (webcam measures YOU first —
#    look straight at the camera, neutral face, good light)
uv run alterego design --like reference.jpg
```

**Named personas (multi-character work):** add `--name` to save into
`identities/<name>.json` instead of the default file:

```powershell
uv run alterego design --name host --jaw 0.6 --save
uv run alterego design --name guest --like portrait.jpg
```

Any command that takes `--identity <name>` uses that persona. Back up
the whole `identities/` folder along with `alterego.json`.

Rules that keep you safe:

- **Same identity in every video, forever.** Consistency is the brand;
  a changed face is a new person to your audience.
- `--like` nudges your *proportions* toward the reference within a
  naturalness budget — it cannot make you look like that person. Use
  AI-generated portraits as references, not real people.
- Redesigning your face never changes your voice (separate voice seed).
- **Characters, not deception.** Playing recurring personas is
  entertainment with deep precedent. Presenting personas as
  independent real people to manufacture credibility is the line this
  tool asks you not to cross.

---

## 3. The social workflow

### Recording

**Webcam + screen** (find device names first):

```powershell
uv run alterego devices                      # exact camera/mic names, in quotes
uv run alterego devices --modes "Integrated Camera"   # what it supports
uv run alterego record --camera "Integrated Camera" --mic "Microphone (Realtek(R) Audio)" --screen
# press Enter to stop; files land in recordings/
```

**Phone (recommended — daylight beats any algorithm):** record outside,
copy via USB (This PC → phone → DCIM), then normalize:

```powershell
uv run alterego prep phone_clip.mp4          # HEVC/variable-fps -> clean 720p H.264
```

> **Light your face.** This is not aesthetic advice, it is a security
> requirement: on dark footage landmark detection fails and frames pass
> through with your REAL face. `disguise` reports coverage and warns
> below 90% — treat that warning as a stop sign.

### One command (recommended)

```powershell
uv run alterego ship take.mp4 --image street.jpg
# runs: disguise -> background -> enhance -> cut(+fillers) -> voice
# output: take_ship.mp4
```

Useful flags: `--night` (underlit salvage), `--no-voice`, `--no-fillers`,
`--no-background`, `--keep` (keep intermediate stage files for inspection).

### Stage by stage (when you want control)

Each stage reads a file, writes a new one with a suffix — run any stage
alone, re-run with different settings for free:

```powershell
uv run alterego disguise take.mp4                          # -> take_alterego.mp4
uv run alterego background take_alterego.mp4 --image sf.jpg    # -> ..._scene.mp4
uv run alterego enhance take_alterego_scene.mp4            # -> ..._graded.mp4
uv run alterego cut take_alterego_scene_graded.mp4 --fillers   # -> ..._tight.mp4
uv run alterego voice take_..._tight.mp4                   # -> ..._voiced.mp4
```

Tuning knobs you'll actually touch:

| Flag | Default | Turn it when… |
|------|---------|---------------|
| `cut --noise-db` | -35 | words got clipped → -45 · dead air survives → -25 |
| `cut --min-silence` | 0.6 | cuts feel robotic-tight → 1.0 |
| `cut --also-cut like basically` | off | your personal crutch words |
| `background --blur` | 31 (own room) / 9 (backdrop) | backdrop looks green-screen → raise |
| `background --harmonize` | 0.4 | composite looks pasted-on → 0.6 · colors look tinted → 0.2 |
| `enhance --night` | off | underlit footage (salvage only — light is better) |

Backdrops: `--image` takes a photo **or a video** (a looping street
plate). Order matters: background before enhance — a shared grade is
what visually glues a composite together.

### Multi-person shots (podcast) and multi-persona shoots

**Two people, one frame** — each person wears their own identity:

```powershell
uv run alterego disguise podcast.mp4 --identity host --identity guest
```

The first `--identity` is the LEFTMOST person; faces are tracked
across frames so identities stick even through brief drop-outs, and
coverage is reported per person. Two rules make it reliable:

1. **Record one audio track per person** (lapel mics, or each side of
   a call). A shared room mic mixes the voices and one pitch shift
   would move both identically. Shift each track with its owner's
   persona (`voice --identity host`), then remix.
2. Seated framing works best. If two people fully cross paths while
   both are hidden, identities can swap — position is the only cue
   (embedding re-ID is roadmapped). Review the output.

**One creator, many characters:** film each take separately and ship
each with a different persona — `ship take1.mp4 --identity host`,
`ship take2.mp4 --identity skeptic` — then cut them together. Same
personas every episode.

### The studio (web UI)

```powershell
uv run alterego studio        # opens http://127.0.0.1:4700 (local only)
```

One dark page, three modes from the bottom dock:

- **IDENTITY** — scan your face once (cached locally, gitignored) and
  it becomes a 3D constellation; the eight faders morph it using the
  SAME math as the real disguise, with points glowing green exactly
  where pixels will move. Name + save personas.
- **STUDIO** — pick a recording, choose personas (comma list for
  multi-person), toggle flags, run Ship/Disguise; the pipeline's real
  output streams into the on-page console.
- **LIVE** — start/stop rehearsal or the virtual camera.

Everything the studio does goes through the same CLI you'd type; it
can never do anything a terminal user couldn't.

### The branded clip

```powershell
uv run alterego clip take_ship.mp4 --title "I built a CV pipeline on 4GB of RAM"
# optional: --handle "@you"   --accent "#39E508"
```

Renders a 9:16 (1080×1920) vertical clip: dark launch look, hook title,
your video in a rounded card, word-timed captions, progress bar. Takes
minutes on a small machine (`--concurrency=1` by design). Restyle it in
`remotion/src/Clip.tsx` — the Python side never needs to change.

**Full journey:** phone clip → `prep` → `ship --image sf.jpg` → `clip
--title "..."` → post.

---

## 4. The live workflow

### Rehearse first (no OBS needed)

```powershell
uv run alterego live --window
```

Your disguised self in a preview window, with the fps counter printing
to the terminal. Expect ~20 fps at the default 640px width on a 4 GB
machine — in a *lit* room. Q quits.

### Stream / video call

```powershell
uv run alterego live                         # -> "OBS Virtual Camera" device
uv run alterego live --image street.jpg      # + backdrop
```

Then in OBS / YouTube Live / Zoom / Meet: select **OBS Virtual Camera**
as the webcam. Never select your real camera in the app — alterego owns
the real camera; apps only ever see the protected feed.

### Live voice

```powershell
uv run alterego live --voice --audio-out "CABLE Input"
```

Then in the streaming/call app, select **CABLE Output** as the
microphone. Your voice is shifted by your identity's factor before any
app hears it.

- Without VB-Cable, `--voice` with no `--audio-out` plays through the
  default speakers — useful to *hear* your alter ego, but it will feed
  back if the mic can hear the speakers. Use headphones.
- Device names: `uv run alterego live --list-audio`

### What fail-closed means (read once, remember forever)

Live has no "review before publish." So when the face tracker loses
you (fast movement, bad light), alterego does NOT show the raw frame —
it pixelates the person region until the face is re-acquired, and the
voice thread outputs silence on any internal error. If you see yourself
pixelate mid-stream: add light, face the camera, it recovers by itself.
Coverage is printed at the end of every session; treat sub-90% sessions
as a lighting problem to fix, not noise to ignore.

Performance levers if fps sags: more light on your face (helps the
camera AND detection), `--width 480`, close Chrome tabs.

---

## 5. Troubleshooting

| Symptom | Cause → fix |
|---------|-------------|
| `ffmpeg not found` | new terminal after `winget install Gyan.FFmpeg`, or `uv sync` (bundled fallback for processing) |
| `record` dies in 2 s: "failed to start" | camera busy (close preview/design/live/Zoom) or unsupported mode → `devices --modes "Camera"` |
| "Could not set video options" | you forced `--size`/`--fps` the camera doesn't offer → drop the flags (native mode is default) |
| ⚠ "face detected on only X%" | footage too dark → re-record with light / outside; `enhance --night` is watchability salvage, not a fix |
| Words clipped after `cut` | quiet mic → `--noise-db -45` |
| `clip`: "Remotion dependencies missing" | `cd remotion; npm install` |
| `clip`: browser download dies repeatedly | fetch `chrome-headless-shell-win64.zip` (version in the error URL) with `curl.exe -L -C - --retry 10 -o shell.zip <url>`, extract into `remotion/node_modules/.remotion/chrome-headless-shell/win64/`, write the version number into `.../chrome-headless-shell/VERSION` |
| `live`: "No virtual camera" | OBS not installed / virtual camera never started once → see setup §1 |
| Live voice echoes/feeds back | shifted audio playing through speakers → headphones, or route to "CABLE Input" |
| Whisper re-downloads or is slow first run | normal: 75 MB model cached after first use |
| Everything slow / swapping | 4 GB reality: close the browser; process at 720p (`prep` default), not 1080p |

## 6. Command reference

| Command | Does | Needs |
|---------|------|-------|
| `devices [--modes CAM]` | list cameras/mics, or a camera's supported modes | ffmpeg |
| `record --camera --mic [--screen]` | record until Enter → `recordings/` | ffmpeg |
| `prep VIDEO` | normalize phone/outside footage to 720p H.264 | ffmpeg |
| `preview` | audition random alter egos (N/K/Q) | webcam |
| `design [--knobs…] [--like PHOTO] [--tweak] [--save]` | craft the identity deliberately | webcam for preview/`--like` |
| `disguise VIDEO` | apply saved identity to a recording | identity |
| `background VIDEO [--image X] [--blur N] [--harmonize F]` | blur room or composite backdrop (photo/video) | — |
| `enhance VIDEO [--night]` | white balance + lighting + color | — |
| `cut VIDEO [--fillers] [--noise-db] [--min-silence] [--also-cut …]` | remove silence (and fillers) | `--fillers`: speech extra |
| `voice VIDEO [--factor F]` | pitch-shift to the alter-ego voice | identity |
| `ship VIDEO [--image X] [--night] [--no-*] [--keep]` | the whole pipeline, one command | identity |
| `clip VIDEO --title "…" [--handle] [--accent]` | branded 9:16 Remotion render | Node + remotion setup, speech extra |
| `live [--window] [--image X] [--voice] [--audio-out DEV] [--width N]` | real-time → virtual camera | live extra; OBS for virtual cam |

Every processing command accepts `--out PATH`; defaults append a suffix
(`take.mp4 → take_alterego.mp4`) so a folder listing tells the story.
