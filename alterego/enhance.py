"""Fix lighting, white balance, and color so footage looks studio-lit.

Township evening light + a cheap webcam usually means: a color cast
(orange bulbs or blue windows), a murky midtone range, and flat color.
Three classic, cheap corrections fix most of it:

  1. Gray-world white balance — removes the color cast.
  2. CLAHE on lightness      — lifts shadows without blowing highlights.
  3. Gentle saturation boost — puts life back after correction.

Each one is a few lines of numpy/OpenCV, and each is a named technique
you can look up — no black boxes.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .video_io import stream_video


def white_balance_grayworld(frame: np.ndarray) -> np.ndarray:
    """Remove color casts using the gray-world assumption.

    The assumption: averaged over a whole scene, the world is roughly
    gray — so if the blue channel averages higher than the others, the
    *light* is blue, not the scene, and we scale it back down.
    """
    means = frame.reshape(-1, 3).mean(axis=0)  # per-channel average (B, G, R)
    gray = means.mean()
    gains = gray / (means + 1e-6)
    # Clip gains so a genuinely colorful scene (big red poster) can't
    # trick the algorithm into an extreme correction.
    gains = np.clip(gains, 0.7, 1.4)
    balanced = frame.astype(np.float32) * gains
    return np.clip(balanced, 0, 255).astype(np.uint8)


def lift_lighting_clahe(frame: np.ndarray, clip_limit: float = 2.0) -> np.ndarray:
    """Brighten murky footage with CLAHE (adaptive histogram equalization).

    Plain "brightness +20" washes out the bright parts of the image.
    CLAHE instead stretches contrast *locally*, tile by tile, so dark
    regions get help and already-bright regions are left alone. We run
    it only on the L (lightness) channel of LAB color space so colors
    themselves don't shift.
    """
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    lightness, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    lab = cv2.merge((clahe.apply(lightness), a, b))
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def boost_saturation(frame: np.ndarray, factor: float = 1.12) -> np.ndarray:
    """Nudge color intensity up. Keep the factor subtle (1.05–1.2):
    past that, skin goes orange and it reads as a filter."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * factor, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def lift_shadows_gamma(frame: np.ndarray, gamma: float = 1.6) -> np.ndarray:
    """Brighten dark footage with gamma correction (a curve, not a +N).

    Gamma raises shadows a lot and highlights barely at all, so faces
    come out of the murk without the bright bits clipping to white.
    Implemented as a 256-entry lookup table: computing the curve once
    and applying it via LUT is ~100x faster than exponentiating every
    pixel — the standard trick for any per-pixel tone function.
    """
    curve = ((np.arange(256) / 255.0) ** (1.0 / gamma) * 255).astype(np.uint8)
    return cv2.LUT(frame, curve)


def denoise_bilateral(frame: np.ndarray) -> np.ndarray:
    """Smooth sensor noise while keeping edges sharp.

    Brightening dark footage also brightens its noise, so night mode
    must denoise. A bilateral filter averages each pixel with its
    neighbours EXCEPT across strong edges — noise melts, features stay.
    """
    return cv2.bilateralFilter(frame, d=5, sigmaColor=40, sigmaSpace=5)


def enhance_frame(frame: np.ndarray, night: bool = False) -> np.ndarray:
    """The full grade, in the order that matters:
    (night: lift shadows, then denoise what the lift amplified,)
    balance color first (so CLAHE works on true tones), then lighting,
    then saturation last (to compensate what correction flattened)."""
    if night:
        frame = lift_shadows_gamma(frame)
        frame = denoise_bilateral(frame)
    frame = white_balance_grayworld(frame)
    frame = lift_lighting_clahe(frame, clip_limit=3.0 if night else 2.0)
    frame = boost_saturation(frame)
    return frame


def process_video(src: str | Path, dst: str | Path, night: bool = False) -> None:
    """Grade a whole recording, preserving audio.

    `night=True` is salvage mode for underlit footage. Honest limits:
    it recovers visibility, not quality — noise eats fine detail, and
    a camera that dropped to 10 fps in the dark stays at 10 fps.
    Real light (or daytime phone footage) beats any algorithm here.
    """
    stream_video(src, dst, lambda frame: enhance_frame(frame, night))
