"""Detect face landmarks with MediaPipe's Face Landmarker task.

MediaPipe gives us 478 numbered points covering the whole face —
jawline, eyes, brows, nose, lips (plus 10 iris points) — at real-time
speed on a CPU. Each landmark index always refers to the same
anatomical spot (e.g. index 152 is always the chin), which is what
lets disguise.py say "move the chin down" and have it hold true on
every frame.

Note: MediaPipe 0.10.35+ removed the old `mp.solutions` API, so this
uses the current "tasks" API. The model weights ship separately as a
small .task file, downloaded once and cached in your home directory.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_CACHE = Path.home() / ".cache" / "alterego" / "face_landmarker.task"


def _ensure_model() -> Path:
    """Download the landmark model once (~3.7 MB), then reuse forever."""
    if not MODEL_CACHE.exists():
        MODEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
        print("Downloading face landmark model (3.7 MB, one time)...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_CACHE)
    return MODEL_CACHE


class FaceLandmarker:
    """Wraps MediaPipe's Face Landmarker to return pixel-coordinate landmarks."""

    def __init__(self, max_faces: int = 1) -> None:
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(_ensure_model())),
            # VIDEO mode tracks the face between frames instead of
            # searching from scratch each time — faster and steadier.
            running_mode=vision.RunningMode.VIDEO,
            num_faces=max_faces,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        # VIDEO mode requires a strictly increasing clock. Frame times
        # don't need to be exact, so we tick a fake 33 ms (≈30 fps).
        self._clock_ms = 0

    def _detect_raw(self, frame_bgr: np.ndarray):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._clock_ms += 33
        return self._landmarker.detect_for_video(image, self._clock_ms)

    def detect(self, frame_bgr: np.ndarray) -> np.ndarray | None:
        """Return a (478, 2) array of [x, y] pixel positions for the
        first face, or None.

        MediaPipe wants RGB and returns coordinates normalized to 0..1,
        so we convert on the way in and scale up on the way out.
        """
        faces = self.detect_all(frame_bgr)
        return faces[0] if faces else None

    def detect_all(self, frame_bgr: np.ndarray) -> list[np.ndarray]:
        """Every detected face's landmarks (up to max_faces), in the
        model's arbitrary order — tracking.py makes the order stable."""
        result = self._detect_raw(frame_bgr)
        height, width = frame_bgr.shape[:2]
        return [
            np.array([[p.x * width, p.y * height] for p in face])
            for face in result.face_landmarks
        ]

    def detect_3d(self, frame_bgr: np.ndarray) -> np.ndarray | None:
        """Like detect(), but keeps MediaPipe's depth estimate as a
        third column — the studio UI's face constellation uses it."""
        result = self._detect_raw(frame_bgr)
        if not result.face_landmarks:
            return None
        height, width = frame_bgr.shape[:2]
        return np.array(
            [[p.x * width, p.y * height, p.z * width] for p in result.face_landmarks[0]]
        )

    def close(self) -> None:
        self._landmarker.close()


class LandmarkSmoother:
    """Smooth landmarks over time with an exponential moving average.

    Detection jitters by a pixel or two every frame. Warping the face
    with raw landmarks makes the whole face shimmer. An EMA — keep
    `alpha` of the new value, `1 - alpha` of the running average —
    damps that jitter while still following real head movement.
    """

    def __init__(self, alpha: float = 0.6) -> None:
        self.alpha = alpha
        self._state: np.ndarray | None = None

    def update(self, landmarks: np.ndarray | None) -> np.ndarray | None:
        if landmarks is None:
            # Face lost (looked away, walked off): reset so we don't
            # blend stale positions when the face comes back.
            self._state = None
            return None
        if self._state is None:
            self._state = landmarks
        else:
            self._state = self.alpha * landmarks + (1 - self.alpha) * self._state
        return self._state
