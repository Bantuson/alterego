# Handoff — studio v5: the prosthetics direction

Written 2026-07-09 at the end of a long session, for the next session
to pick up. Read this together with docs/GUIDE.md (operating manual),
PRODUCT.md / DESIGN.md (design contract), and the project memory.

## Where things stand

Everything through studio v4 is committed and pushed (`9580e0b`).
57 tests green. The engine (record/prep → disguise (multi-person) →
background → enhance → cut → voice → clip → ship → live) is solid and
CLI-verified. The studio UI has had four rounds; the user is still
not satisfied — the parts exist but the FLOW fails. His words:
"modals just aren't working for this interface."

## Bugs the user hit in v4 (fix first, they're quick)

1. **Setup never appeared for him.** Root cause: setup only triggers
   when ZERO personas exist, and he already has `alterego.json` +
   `identities/trial1.json`. Design miss, not a code bug. Fix: setup
   should key on whether a HEAD SCAN exists (see new direction), and
   be re-enterable from the UI at any time.
2. **Never saw the mirror.** The MESH|MIRROR toggle sits inside the
   Identity panel and defaults to MESH; nothing pulls the user to it.
   The mirror must be the default centerpiece of the identity journey,
   not a toggle you must discover.
3. **Live: no identity chooser.** It's a free-text field; should be
   persona chips (same component as Identity).
4. **Backdrop "does not work".** Likely real bug: in
   `studio.py:preview_frames`, if the backdrop path doesn't exist,
   `BackdropSource` raises INSIDE the generator and the stream dies
   silently — the browser shows nothing and no error surfaces.
   Validate the path before streaming; return a console-visible error.
   Same validation for /api/live/start.
5. **Rehearse window is confusing.** It opens an OpenCV window OUTSIDE
   the browser with no explanation. With the in-browser mirror, the
   rehearse button is redundant — remove it; the mirror IS rehearsal.

## The new product direction (user's spec, distilled)

### 1. Setup = capture the head, once
Initial setup should take short videos/snapshots of the face CLOSE UP
at different angles, extract the full head structure, and save that
as "main". Every alter ego is then an OFFSET from that original.

Technical pointers:
- Capture flow: guided prompts ("look left… right… up…"), grab N
  frames per pose from the webcam, run the existing
  `FaceLandmarker.detect_3d` per frame.
- Fusing angles: align each frame's landmarks to a reference pose via
  similarity transform (Procrustes — scale+rotation+translation on
  the 3D points), then average. Yaw from MediaPipe's own geometry or
  from left/right cheek z-difference.
- Storage: head structure is BIOMETRIC data → keep in
  `.alterego-cache/head.json` (already gitignored), NOT inside
  identity files. Identities stay as offsets (knobs), so they remain
  shareable-ish and the biometric never leaves the cache.
- The existing single-frame scan becomes a fallback ("quick scan").

### 2. "Digital prosthetic makeup" — appearance layers
Beyond geometry, the studio should do what a makeup artist does:
**beard, skin tone, eye color, lip color, skin texture** — visible on
the centerpiece (which for appearance means the MIRROR, since these
are pixel effects, not point effects).

Feasibility per feature (all CPU-viable, all landmark-anchored):
- **Lip color / eye color**: polygon masks from the landmark contours
  (lips indices already in `topology.js` CONTOURS; iris = landmarks
  468–477), feathered, hue/chroma shift in LAB or HSV. Easy, high wow.
- **Skin tone**: person/face-region mask (segmentation ∩ face oval
  polygon), gentle LAB a/b + L shifts — reuse the `harmonize` math.
- **Skin texture**: subtle bilateral smoothing or noise within the
  face mask (the enhance module has the denoise primitives).
- **Beard**: the hard one. v1 = procedural stubble: jaw/chin region
  from the face-oval landmarks, darken + high-frequency noise mask,
  density knob. Will look stylized; be honest about it and iterate.
  (True hair synthesis is GAN territory — out of scope on 4 GB.)
- Schema: identity files grow an `appearance` block alongside the
  geometry knobs — `{"profile": {...8 knobs}, "appearance":
  {"lip_color": [h,s], "eye_color": ..., "beard": 0..1, ...},
  "voice_seed": N}`. MIGRATE OLD FILES (profile-only) exactly like
  the seed→knobs migration — published faces must not move.
- Implementation home: a new `alterego/makeup.py` applied inside
  `LivePipeline.process` (after warp, before grade) and as a post
  stage; the mirror then previews it live for free.

### 3. Two journeys, explicitly
- **The single-alterego journey** (most users): setup head → shape
  ONE identity (geometry + prosthetics) → studio/live always use it.
- **The wardrobe** (multi-persona creators): a separate management
  surface for creating, comparing, and assigning multiple personas
  (the multi-person disguise engine already supports them).

### 4. UI architecture rethink
Stop using side panels ("modals"). Make each dock mode a FULL surface:
- IDENTITY: mirror (or mesh) center-left as the hero, desk docked
  right as part of the page, not floating over it.
- The centerpiece should always reflect the SAVED identity being
  worked on (he said: "mirror in centerpiece derived from saved
  identity" — load selected persona's knobs into both mesh and mirror
  automatically).
- Keep: the instrument aesthetic (graticule/reticle/readouts), the
  semantic accents (cyan action / green data / amber warn / red live),
  the mixing desk, the fail-closed messaging. Those landed.

## Environment gotchas (save yourself an hour)

- His screen is ~1366×768 — verify every UI change at that size.
- Screenshots: `?demo[=studio|live]` or `?hold` + the `/slow?ms=N`
  load-hold endpoint; chrome-headless-shell at
  `remotion/node_modules/.remotion/chrome-headless-shell/win64/...`
  with `--timeout=15000`, WITHOUT `--virtual-time-budget` (hangs
  intermittently). First attempt after a server restart may hang —
  kill `chrome-headless-shell` processes and retry. `?demo` must
  never touch the real camera (privacy guard in `startMirror`).
- Server changes need a restart; UI files (`alterego/ui/*`) are
  re-read per request.
- PowerShell: no `&&`, no double quotes inside `@'...'@` commit
  messages passed to git (native-arg quoting bug splits them).
- His identity: legacy `alterego.json` `{"seed": 90719}` — migration
  path must keep working. `identities/trial1.json` exists (all-zero
  knobs, probably a test — ask before treating it as meaningful).
- Commit style: micro commits, conventional prefixes, educational
  code comments, uv not pip. He reads the code to learn — keep it
  teachable.

## Suggested order of work

1. Quick bug fixes (list above) — restores trust in what exists.
2. UI re-architecture to full surfaces + mirror-as-centerpiece.
3. Head-capture setup flow (multi-angle → fused head → saved once).
4. Appearance layers: lips + eyes + tone first (easy, high impact),
   texture next, beard last (hardest, set expectations).
5. The wardrobe surface for multi-persona management.
6. Update GUIDE.md + rebuild-guide.html as features land.
