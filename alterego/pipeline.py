"""One command from raw take to postable video: `alterego ship`.

Runs the whole pipeline in the order that matters:

    disguise -> background -> enhance -> cut -> voice

Why this order:
  * disguise FIRST — landmark detection works best on the original,
    un-processed pixels.
  * background before enhance — grading after compositing gives the
    subject and backdrop a shared color treatment (the "glue").
  * cut before voice — the filler transcription hears your natural
    voice, which whisper understands best; the shift comes after.

Every stage still writes a real file (in a temp folder), so a crash
mid-ship loses nothing but time, and --keep lets you inspect the
intermediate steps when debugging.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .settings import load_identity


def ship(
    src: str | Path,
    out: str | Path | None = None,
    image: str | Path | None = None,
    night: bool = False,
    fillers: bool = True,
    voice: bool = True,
    background: bool = True,
    keep: bool = False,
) -> Path:
    """Run every stage back to back. Returns the final path."""
    src = Path(src)
    final = Path(out) if out else src.with_name(f"{src.stem}_ship{src.suffix}")

    identity = load_identity()
    if identity is None:
        raise SystemExit(
            "ship needs your saved identity (seed). Run `alterego preview` "
            "and press K on the face you want."
        )
    seed, strength = identity

    # Build the stage list up front so we can show honest progress.
    stages: list[str] = ["disguise"]
    if background:
        stages.append("background")
    stages.append("enhance")
    stages.append("cut")
    if voice:
        stages.append("voice")

    workdir = Path(tempfile.mkdtemp(prefix="alterego_ship_")) if not keep else (
        final.parent / f"{src.stem}_ship_steps"
    )
    workdir.mkdir(exist_ok=True)

    def step_path(index: int, name: str) -> Path:
        return workdir / f"{index:02d}_{name}{src.suffix}"

    current = src
    try:
        for index, stage in enumerate(stages, start=1):
            is_last = index == len(stages)
            target = final if is_last else step_path(index, stage)
            print(f"[{index}/{len(stages)}] {stage}")

            if stage == "disguise":
                from .disguise import process_video

                process_video(current, target, seed=seed, strength=strength)
            elif stage == "background":
                from .background import process_video

                process_video(current, target, image=image)
            elif stage == "enhance":
                from .enhance import process_video

                process_video(current, target, night=night)
            elif stage == "cut":
                from .cuts import process_video

                process_video(current, target, cut_fillers=fillers)
            elif stage == "voice":
                from .voice import factor_from_seed, process_video

                process_video(current, target, factor_from_seed(seed))
            current = target
    finally:
        if not keep:
            for leftover in workdir.glob("*"):
                if leftover != final:
                    leftover.unlink(missing_ok=True)
            workdir.rmdir()

    print(f"\n✓ shipped: {final}")
    return final
