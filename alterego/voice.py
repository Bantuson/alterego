"""Shift your voice so it identifies your alter ego, not you.

The face disguise leaves your biggest identifier untouched: voice.
A pitch shift of a few percent changes how you sound while keeping
speech perfectly intelligible — the audio version of what disguise.py
does to facial proportions.

Just like the face, the voice must be CONSISTENT: the shift factor is
derived from your identity seed, so every video you ever publish has
the same alter-ego voice.

Honest limits (same spirit as the face disguise): this defeats casual
recognition ("hey, that sounds like...") and shifts your voiceprint;
it is not proof against determined forensic analysis. Speech *content*
— names, places, your story — identifies you more than timbre does.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .ffmpeg_tools import find_ffmpeg, run_ffmpeg

# Salt mixed with the seed so voice and face draw DIFFERENT random
# numbers from the same identity. Without it, correlated draws would
# tie voice pitch to jaw width for every seed.
VOICE_SALT = 7


def factor_from_seed(seed: int) -> float:
    """Derive the pitch factor (e.g. 1.05 = 5% up) from the identity seed.

    We sample the shift's SIZE between 3% and 7%, then flip a coin for
    direction. Sampling naively in [0.93, 1.07] could land on ~1.00 —
    a disguise that does nothing — so the dead zone is designed out.
    """
    rng = np.random.default_rng([seed, VOICE_SALT])
    magnitude = rng.uniform(0.03, 0.07)
    direction = 1.0 if rng.random() < 0.5 else -1.0
    return float(round(1.0 + direction * magnitude, 4))


def _has_rubberband() -> bool:
    """Check whether this ffmpeg build ships the Rubber Band filter."""
    import subprocess

    result = subprocess.run(
        [find_ffmpeg(), "-hide_banner", "-filters"], capture_output=True, text=True
    )
    return "rubberband" in result.stdout


def pitch_filter(factor: float, use_rubberband: bool) -> str:
    """Build the ffmpeg audio-filter string for a pitch shift.

    Two implementations, best first:
      * rubberband — a proper pitch-shifting library: changes pitch,
        keeps duration, minimal artifacts. In full ffmpeg builds.
      * asetrate chain — the classic fallback: resample the audio
        faster (pitch AND speed go up), then atempo slows it back
        down. Slightly more artifacts, works everywhere.
    """
    if use_rubberband:
        return f"rubberband=pitch={factor}"
    return f"aresample=48000,asetrate={int(48000 * factor)},aresample=48000,atempo={1 / factor:.6f}"


def process_video(src: str | Path, dst: str | Path, factor: float) -> None:
    """Re-encode the audio with the pitch shift; video is copied as-is
    (`-c:v copy` = no quality loss, no re-encode time)."""
    audio_filter = pitch_filter(factor, _has_rubberband())
    print(f"  shifting pitch x{factor} ({audio_filter.split('=')[0]})")
    run_ffmpeg(
        [
            "-y",
            "-i", str(src),
            "-af", audio_filter,
            "-c:v", "copy",
            "-c:a", "aac",
            str(dst),
        ]
    )
    print(f"  saved {dst}")
