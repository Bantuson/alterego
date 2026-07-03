"""Detect face landmarks with MediaPipe Face Mesh.

MediaPipe gives us 468 numbered points covering the whole face —
jawline, eyes, brows, nose, lips — at real-time speed on a CPU.
Each landmark index always refers to the same anatomical spot
(e.g. index 152 is always the chin), which is what lets disguise.py
say "move the chin down" and have it hold true on every frame.
"""

from __future__ import annotations

import numpy as np

# MediaPipe prints noisy TensorFlow-style logs on import; this is the
# documented way to import the legacy "solutions" API.
import mediapipe as mp


class FaceLandmarker:
    """Wraps MediaPipe Face Mesh to return pixel-coordinate landmarks."""

    def __init__(self) -> None:
        self._mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,  # video mode: track between frames (faster)
            max_num_faces=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def detect(self, frame_bgr: np.ndarray) -> np.ndarray | None:
        """Return a (468, 2) array of [x, y] pixel positions, or None.

        MediaPipe wants RGB and returns coordinates normalized to 0..1,
        so we convert on the way in and scale up on the way out.
        """
        rgb = frame_bgr[:, :, ::-1]  # BGR -> RGB by reversing channels
        result = self._mesh.process(rgb)
        if not result.multi_face_landmarks:
            return None

        height, width = frame_bgr.shape[:2]
        landmarks = result.multi_face_landmarks[0].landmark
        return np.array([[p.x * width, p.y * height] for p in landmarks])

    def close(self) -> None:
        self._mesh.close()


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
