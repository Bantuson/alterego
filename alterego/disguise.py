"""Warp facial geometry so you look naturally different on camera.

The idea
--------
Face recognition (human and machine) keys on the *proportions* between
features: jaw width, eye spacing, nose length, mouth width. If we nudge
each of those by a few percent — consistently, on every frame — the
face still looks human and moves naturally, but it reads as a
different person. No deep learning, no face swap: pure geometry.

How it works, per frame:
  1. faces.py gives us 468 landmarks (pixel positions of face parts).
  2. A DisguiseProfile (seeded random, so it's the SAME alter ego every
     video) says how far to push each feature, in units of face width.
  3. We turn those pushes into a smooth displacement field — imagine
     Photoshop's Liquify tool: each control point drags the pixels near
     it, with a Gaussian falloff so the effect fades out smoothly.
  4. cv2.remap applies the field. Skin texture, lighting, expressions,
     and lip-sync are untouched because pixels only *move*, they are
     never invented.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import cv2
import numpy as np

from .faces import FaceLandmarker, LandmarkSmoother
from .video_io import stream_video

# MediaPipe Face Mesh landmark indices for the anatomy we move.
# (The mesh has 468 points; these indices are fixed by the model.)
POINT = {
    "chin": 152,
    "jaw_left": 397, "jaw_right": 172,
    "cheek_left": 454, "cheek_right": 234,
    "nose_tip": 4, "nose_bridge": 6,
    "nostril_left": 327, "nostril_right": 98,
    "eye_outer_left": 263, "eye_inner_left": 362,
    "eye_outer_right": 33, "eye_inner_right": 133,
    "mouth_left": 291, "mouth_right": 61,
    "lip_top": 13, "lip_bottom": 14,
    "brow_left": 334, "brow_right": 105,
}


@dataclass
class DisguiseProfile:
    """One alter ego: how far each feature moves, as a fraction of face width.

    Values are dimensionless multipliers in roughly -1..1; the actual
    pixel distances are computed per frame from the measured face width,
    so the disguise scales correctly when you lean toward the camera.
    """

    jaw_width: float
    chin_length: float
    eye_spacing: float
    nose_length: float
    nose_width: float
    mouth_width: float
    lip_fullness: float
    brow_height: float

    @classmethod
    def from_seed(cls, seed: int, strength: float = 1.0) -> "DisguiseProfile":
        """Generate a reproducible alter ego from a seed number.

        Same seed -> same random draws -> same face changes in every
        video you ever publish. Your alter ego needs to be consistent
        or viewers will notice. Keep your seed secret like a password.
        """
        rng = np.random.default_rng(seed)
        values = rng.uniform(-1.0, 1.0, size=len(fields(cls))) * strength
        return cls(*values)


def control_shifts(landmarks: np.ndarray, profile: DisguiseProfile) -> tuple[np.ndarray, np.ndarray]:
    """Turn a profile into concrete (points, pixel_shifts) for this frame.

    Each rule below is one line of "facial anthropometry": which
    landmark moves, along which axis, scaled by which profile knob.
    The magic numbers (0.02–0.05) cap each change at a few percent of
    face width — enough to change identity, small enough to look real.
    """
    p = {name: landmarks[i] for name, i in POINT.items()}
    face_width = np.linalg.norm(p["cheek_left"] - p["cheek_right"])
    face_center_x = (p["cheek_left"][0] + p["cheek_right"][0]) / 2

    def outward(point: np.ndarray) -> float:
        """+1 if this point is on the left half of the face, else -1,
        so 'wider' pushes both sides away from the center line."""
        return 1.0 if point[0] > face_center_x else -1.0

    moves: list[tuple[str, float, float]] = []  # (point name, dx, dy)

    # Jawline: wider/narrower. Cheeks move half as much as the jaw so
    # the outline stays a smooth curve instead of getting dents.
    jaw = profile.jaw_width * 0.04 * face_width
    for name in ("jaw_left", "jaw_right"):
        moves.append((name, jaw * outward(p[name]), 0))
    for name in ("cheek_left", "cheek_right"):
        moves.append((name, jaw * 0.5 * outward(p[name]), 0))

    # Chin: longer/shorter face.
    moves.append(("chin", 0, profile.chin_length * 0.05 * face_width))

    # Eyes: closer together / farther apart (a strong identity cue).
    eye = profile.eye_spacing * 0.02 * face_width
    for name in ("eye_outer_left", "eye_inner_left", "eye_outer_right", "eye_inner_right"):
        moves.append((name, eye * outward(p[name]), 0))

    # Nose: length (tip down/up) and width (nostrils out/in).
    moves.append(("nose_tip", 0, profile.nose_length * 0.04 * face_width))
    nose_w = profile.nose_width * 0.03 * face_width
    for name in ("nostril_left", "nostril_right"):
        moves.append((name, nose_w * outward(p[name]), 0))

    # Mouth: width and lip fullness.
    mouth = profile.mouth_width * 0.03 * face_width
    for name in ("mouth_left", "mouth_right"):
        moves.append((name, mouth * outward(p[name]), 0))
    lip = profile.lip_fullness * 0.015 * face_width
    moves.append(("lip_top", 0, -lip))
    moves.append(("lip_bottom", 0, lip))

    # Brows: height changes the whole expression "resting state".
    brow = profile.brow_height * 0.025 * face_width
    moves.append(("brow_left", 0, -brow))
    moves.append(("brow_right", 0, -brow))

    points = np.array([p[name] for name, _, _ in moves], dtype=np.float32)
    shifts = np.array([[dx, dy] for _, dx, dy in moves], dtype=np.float32)
    return points, shifts


def displacement_field(
    shape: tuple[int, int],
    points: np.ndarray,
    shifts: np.ndarray,
    sigma: float,
    scale: float = 0.25,
) -> tuple[np.ndarray, np.ndarray]:
    """Build a dense "where should each pixel sample from" map.

    For every pixel we sum each control point's shift, weighted by a
    Gaussian of the distance to that point — near a control point you
    get its full shift, far away you get nothing, in between you get a
    smooth blend. That smoothness is what keeps the warp organic.

    Performance note: computing this for every pixel of a 720p frame
    is expensive, so we compute it on a grid `scale` times smaller and
    let cv2.resize interpolate it back up. Displacement fields are
    smooth by construction, so the upscaling is visually lossless —
    a classic real-world CV optimization.
    """
    height, width = shape
    small_h, small_w = int(height * scale), int(width * scale)

    ys, xs = np.mgrid[0:small_h, 0:small_w].astype(np.float32)
    field_x = np.zeros((small_h, small_w), np.float32)
    field_y = np.zeros((small_h, small_w), np.float32)
    weight_sum = np.zeros((small_h, small_w), np.float32)

    two_sigma_sq = 2 * (sigma * scale) ** 2
    for (px, py), (dx, dy) in zip(points * scale, shifts * scale):
        dist_sq = (xs - px) ** 2 + (ys - py) ** 2
        weight = np.exp(-dist_sq / two_sigma_sq)
        field_x += weight * dx
        field_y += weight * dy
        weight_sum += weight

    # Where control points overlap, weights can sum past 1 and would
    # over-shift pixels; divide those regions back down to an average.
    overlap = np.maximum(weight_sum, 1.0)
    field_x /= overlap
    field_y /= overlap

    # Upsample the small field to full resolution. The shifts were
    # computed in downscaled pixels, so divide by `scale` to restore
    # their true pixel length.
    field_x = cv2.resize(field_x, (width, height)) / scale
    field_y = cv2.resize(field_y, (width, height)) / scale
    return field_x, field_y


def apply_disguise(frame: np.ndarray, landmarks: np.ndarray, profile: DisguiseProfile) -> np.ndarray:
    """Warp one frame according to the profile."""
    points, shifts = control_shifts(landmarks, profile)
    face_width = np.linalg.norm(
        landmarks[POINT["cheek_left"]] - landmarks[POINT["cheek_right"]]
    )

    # remap() is a BACKWARD warp: for each output pixel it asks "which
    # input pixel do I show?". To push a feature +d we therefore sample
    # from -d, hence the minus sign on the shifts.
    field_x, field_y = displacement_field(
        frame.shape[:2], points, -shifts, sigma=face_width * 0.18
    )

    height, width = frame.shape[:2]
    grid_x, grid_y = np.meshgrid(
        np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32)
    )
    return cv2.remap(
        frame,
        grid_x + field_x,
        grid_y + field_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )


def process_video(src: str | Path, dst: str | Path, seed: int, strength: float = 1.0) -> None:
    """Run the disguise over a whole recording, preserving audio.

    Frames where no face is detected pass through untouched — that is
    the safe default for screen-share segments or empty-chair moments.
    """
    profile = DisguiseProfile.from_seed(seed, strength)
    landmarker = FaceLandmarker()
    smoother = LandmarkSmoother()
    counts = {"total": 0, "disguised": 0}

    def disguise_frame(frame: np.ndarray) -> np.ndarray:
        counts["total"] += 1
        landmarks = smoother.update(landmarker.detect(frame))
        if landmarks is None:
            return frame
        counts["disguised"] += 1
        return apply_disguise(frame, landmarks, profile)

    try:
        stream_video(src, dst, disguise_frame)
    finally:
        landmarker.close()

    # Silent passthrough is a PRIVACY failure: every frame without a
    # detected face went through with your real face untouched. Make
    # low coverage impossible to miss.
    coverage = counts["disguised"] / max(counts["total"], 1)
    if coverage < 0.9:
        print(
            f"⚠ face detected on only {coverage:.0%} of frames — the rest "
            f"show your REAL face. Common cause: footage too dark. "
            f"Try `enhance --night` BEFORE disguise, or re-record with light."
        )
    else:
        print(f"  disguise covered {coverage:.0%} of frames")
