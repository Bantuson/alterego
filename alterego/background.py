"""Replace or blur the background — your environment stays private too.

MediaPipe's selfie segmentation model gives a per-pixel probability
that a pixel is you. With that mask we can composite you over any
backdrop, or blur your real room into anonymous bokeh.

Realism rules (learned the hard way by every YouTuber):
  * A SHARP fake background screams green-screen. A blurred one reads
    as "shot on a phone in portrait mode" — instantly plausible.
  * Light direction must roughly match: footage shot in daylight
    composites believably onto a daytime street; your night bedroom
    onto a sunny street does not.
  * Grade AFTER compositing (run `enhance` on the output) so subject
    and backdrop share the same color treatment — shared grade is
    what visually "glues" a composite together.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

from .video_io import stream_video

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
    "selfie_segmenter/float16/latest/selfie_segmenter.tflite"
)
MODEL_CACHE = Path.home() / ".cache" / "alterego" / "selfie_segmenter.tflite"


def _ensure_model() -> Path:
    if not MODEL_CACHE.exists():
        MODEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
        print("Downloading segmentation model (one time)...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_CACHE)
    return MODEL_CACHE


class PersonSegmenter:
    """Per-frame person mask: float array, 1.0 = definitely you."""

    def __init__(self) -> None:
        options = vision.ImageSegmenterOptions(
            base_options=BaseOptions(model_asset_path=str(_ensure_model())),
            running_mode=vision.RunningMode.VIDEO,
            output_confidence_masks=True,
        )
        self._segmenter = vision.ImageSegmenter.create_from_options(options)
        self._clock_ms = 0

    def mask(self, frame_bgr: np.ndarray) -> np.ndarray:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._clock_ms += 33
        result = self._segmenter.segment_for_video(image, self._clock_ms)
        # The selfie model outputs one confidence mask: foreground (you).
        # It arrives as (H, W, 1); squeeze to a plain (H, W) float image.
        return np.squeeze(result.confidence_masks[0].numpy_view()).copy()

    def close(self) -> None:
        self._segmenter.close()


def feather(mask: np.ndarray, radius: int = 7) -> np.ndarray:
    """Soften the mask edge so hair and shoulders blend instead of
    being scissor-cut. Radius is in pixels; odd kernel required."""
    kernel = radius * 2 + 1
    return cv2.GaussianBlur(mask, (kernel, kernel), 0)


def fit_to_frame(background: np.ndarray, width: int, height: int) -> np.ndarray:
    """Scale-and-center-crop a backdrop to the video's size, keeping its
    aspect ratio (a stretched street looks wrong immediately)."""
    bg_h, bg_w = background.shape[:2]
    scale = max(width / bg_w, height / bg_h)
    resized = cv2.resize(background, (int(bg_w * scale) + 1, int(bg_h * scale) + 1))
    y = (resized.shape[0] - height) // 2
    x = (resized.shape[1] - width) // 2
    return resized[y : y + height, x : x + width]


def composite(frame: np.ndarray, mask: np.ndarray, background: np.ndarray) -> np.ndarray:
    """Alpha-blend: person where mask≈1, backdrop where mask≈0."""
    alpha = mask[:, :, np.newaxis]  # add a channel axis to broadcast over BGR
    blended = frame.astype(np.float32) * alpha + background.astype(np.float32) * (1 - alpha)
    return blended.astype(np.uint8)


def process_video(
    src: str | Path,
    dst: str | Path,
    image: str | Path | None = None,
    blur: int | None = None,
) -> None:
    """Swap the background for `image`, or blur the real one if no image.

    `blur` controls the backdrop's Gaussian blur. Defaults: heavy (31)
    when hiding your real room, light (9) on a replacement image —
    just enough to sell the "portrait mode" depth illusion.
    """
    segmenter = PersonSegmenter()
    backdrop: np.ndarray | None = None
    if image is not None:
        backdrop = cv2.imread(str(image))
        if backdrop is None:
            raise FileNotFoundError(f"Could not read background image: {image}")
    blur = blur if blur is not None else (9 if backdrop is not None else 31)
    kernel = blur * 2 + 1  # blur amount -> odd Gaussian kernel size

    fitted: np.ndarray | None = None  # backdrop resized once, on first frame

    def swap_background(frame: np.ndarray) -> np.ndarray:
        nonlocal fitted
        height, width = frame.shape[:2]
        if backdrop is not None:
            if fitted is None:
                fitted = fit_to_frame(backdrop, width, height)
                if blur > 0:
                    fitted = cv2.GaussianBlur(fitted, (kernel, kernel), 0)
            bg = fitted
        else:
            # No image given: the "backdrop" is your own room, blurred
            # beyond recognition. Privacy with zero setup.
            bg = cv2.GaussianBlur(frame, (kernel, kernel), 0)
        mask = feather(segmenter.mask(frame))
        return composite(frame, mask, bg)

    try:
        stream_video(src, dst, swap_background)
    finally:
        segmenter.close()
