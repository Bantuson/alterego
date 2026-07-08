"""Design your alter ego instead of rolling dice for one.

The disguise has exactly eight degrees of freedom (the knobs on
DisguiseProfile), which means "the face I want" is always, in the
end, eight numbers. Two ways to choose them deliberately:

  * Explicit knobs — "stronger jaw, wider-set eyes" is literally
    `--jaw 0.8 --eyes-apart 0.6`.
  * A reference face — measure the reference's facial RATIOS with
    the same landmark model the disguise uses, measure yours, and
    set each knob to move your ratio toward the reference's.

Honest scope: the warp moves features a few percent of face width,
so a reference nudges you toward someone's PROPORTIONS — it cannot
make you look like them. That is a feature: it keeps the result
natural and keeps this tool out of deepfake territory. Prefer
synthetic reference faces (AI-generated portraits) over real
people's photos.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .disguise import POINT, DisguiseProfile
from .faces import FaceLandmarker


def measure_ratios(landmarks: np.ndarray) -> dict[str, float]:
    """Reduce a face to the eight ratios the disguise can influence.

    Every measurement is divided by cheek-to-cheek face width, which
    makes the numbers dimensionless: comparable between photos taken
    at different distances, resolutions, or zoom levels.
    """
    p = {name: landmarks[i] for name, i in POINT.items()}
    face_width = float(np.linalg.norm(p["cheek_left"] - p["cheek_right"]))

    def dist(a: str, b: str) -> float:
        return float(np.linalg.norm(p[a] - p[b])) / face_width

    brow_lift = (
        abs(p["brow_left"][1] - p["eye_outer_left"][1])
        + abs(p["brow_right"][1] - p["eye_outer_right"][1])
    ) / (2 * face_width)

    return {
        "jaw_width": dist("jaw_left", "jaw_right"),
        "chin_length": dist("chin", "lip_bottom"),
        "eye_spacing": dist("eye_inner_left", "eye_inner_right"),
        "nose_length": dist("nose_bridge", "nose_tip"),
        "nose_width": dist("nostril_left", "nostril_right"),
        "mouth_width": dist("mouth_left", "mouth_right"),
        "lip_fullness": dist("lip_top", "lip_bottom"),
        "brow_height": brow_lift,
    }


# How much a knob at full strength (1.0) can change each ratio,
# relative to the ratio itself. Derived from the shift constants in
# control_shifts (e.g. jaw moves 0.04*face_width per side) divided by
# a typical ratio value. Approximate on purpose: the preview window,
# not this table, is the final judge of the result.
KNOB_GAIN = {
    "jaw_width": 0.09,
    "chin_length": 0.35,
    "eye_spacing": 0.13,
    "nose_length": 0.16,
    "nose_width": 0.20,
    "mouth_width": 0.13,
    "lip_fullness": 0.50,
    "brow_height": 0.50,
}


def knobs_from_reference(
    mine: dict[str, float], target: dict[str, float]
) -> DisguiseProfile:
    """Set each knob to push my ratio toward the target's ratio.

    relative gap = (target - mine) / mine   ("their jaw is 6% wider")
    knob        = gap / gain, clamped to ±1 (the naturalness budget)

    The clamp is doing real work: if the reference's proportions are
    far from yours, the disguise moves you as far as it can while
    still looking natural — it does not try to hit an impossible
    target and produce an uncanny face.
    """
    values = {}
    for name, gain in KNOB_GAIN.items():
        gap = (target[name] - mine[name]) / max(mine[name], 1e-6)
        values[name] = float(np.clip(gap / gain, -1.0, 1.0))
    return DisguiseProfile.from_dict(values)


def landmarks_from_image(path: str | Path) -> np.ndarray:
    """Detect landmarks in a photo (the reference face)."""
    image = cv2.imread(str(path))
    if image is None:
        raise SystemExit(f"Could not read image: {path}")
    landmarker = FaceLandmarker()
    try:
        landmarks = landmarker.detect(image)
    finally:
        landmarker.close()
    if landmarks is None:
        raise SystemExit(f"No face found in {path} — use a clear, front-facing photo.")
    return landmarks


def landmarks_from_camera(camera_index: int = 0, samples: int = 15) -> np.ndarray:
    """Measure YOUR face by averaging several webcam frames.

    A single frame carries detection jitter and whatever expression
    you happened to make; averaging ~15 frames gives a stable
    baseline. Look straight at the camera with a neutral face.
    """
    capture = cv2.VideoCapture(camera_index)
    if not capture.isOpened():
        raise SystemExit(f"No webcam at index {camera_index}.")
    landmarker = FaceLandmarker()
    collected: list[np.ndarray] = []
    attempts = 0
    try:
        while len(collected) < samples and attempts < samples * 10:
            ok, frame = capture.read()
            attempts += 1
            if not ok:
                break
            landmarks = landmarker.detect(frame)
            if landmarks is not None:
                collected.append(landmarks)
    finally:
        capture.release()
        landmarker.close()
    if len(collected) < samples // 2:
        raise SystemExit(
            "Could not see your face reliably — light your face and look at the camera."
        )
    return np.mean(collected, axis=0)
