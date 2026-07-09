# Design

## Theme

Dark, singular, instrument-like. One room: a near-black blue void lit
by the face constellation. No white chrome anywhere. Depth comes from
the 3D scene, not from card stacks or glass.

## Color

OKLCH-first; hex given for canvas/three contexts.

- `--bg`        oklch(0.13 0.02 265)  ≈ #070a15 — the room
- `--surface`   oklch(0.18 0.025 265) ≈ #0e1322 — docks, panels
- `--line`      oklch(0.30 0.03 265)  ≈ #232c47 — hairline borders
- `--ink`       oklch(0.93 0.01 265)  ≈ #e8ebf4 — primary text
- `--muted`     oklch(0.68 0.02 265)  ≈ #9aa2b8 — secondary text (≥4.5:1 on bg)
- `--accent`    oklch(0.82 0.26 140)  ≈ #39E508 — THE brand green. Active
  states, live indicators, save actions, the constellation's ignition.
  Never decoration; if it glows green, it is on.
- `--warn`      oklch(0.75 0.15 60)   ≈ #ffb347 — coverage warnings
- `--danger`    oklch(0.65 0.2 25)    ≈ #ff6b6b — fail-closed, stop states

Strategy: Restrained (product register). Accent ≤10% of any view.

## Typography

- Display/headers: "Segoe UI Variable Display", "Segoe UI", system-ui —
  weight contrast does the work (200 for the wordmark, 600 for labels).
- Data/labels/console: "Cascadia Code", Consolas, monospace. Knob
  values, file paths, job logs, coordinates are ALWAYS mono.
- Fixed rem scale, ratio ~1.2. No fluid clamp in panels.

## Layout

Single full-viewport page. Three.js canvas is the root layer; UI
floats above it in fixed regions:

- Top-left: wordmark + local-only pledge (one line).
- Bottom-center: the dock — three verbs (IDENTITY · STUDIO · LIVE).
  Exactly one panel open at a time; ESC closes to the empty room.
- Right rail (IDENTITY): 8 vertical knob faders + name + save.
- Left rail (IDENTITY): saved persona chips.
- Left overlay (STUDIO/LIVE): job console, mono, no fading toasts.

## Motion

- Constellation: ambient drift + mouse parallax; springs (stiffness
  ~60, damping ~12) when knobs change or a scan lands. This is state
  visualization, not decoration: the springs show the warp settling.
- Panels: 180ms ease-out-quart slide + fade.
- `prefers-reduced-motion`: ambient drift and parallax off; springs
  become instant sets; panel transitions become fades.

## Components

- Fader: 1px track, mono value readout, accent fill only while
  dragging or non-zero.
- Chip: persona name in mono, 1px border, accent border when selected.
- Console: bottom-left, mono 12px, max 12 lines, warnings in --warn
  and pinned (never auto-dismissed).
- Buttons: solid --surface, 1px --line border, no shadows; the single
  primary action per panel may use accent fill with black text.
