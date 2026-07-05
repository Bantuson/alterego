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


def harmonize(frame: np.ndarray, backdrop: np.ndarray, amount: float = 0.4) -> np.ndarray:
    """Nudge the subject's colors toward the backdrop's palette.

    This is (a gentle version of) Reinhard color transfer: match the
    mean and spread of each LAB channel to the backdrop's statistics.
    Composites fail the eye when subject and scene disagree about what
    color the light is — this makes them agree. `amount` blends between
    untouched (0.0) and fully matched (1.0); full transfer looks like a
    tint, ~0.4 just makes the light plausible.
    """
    if amount <= 0:
        return frame
    frame_lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB).astype(np.float32)
    backdrop_lab = cv2.cvtColor(backdrop, cv2.COLOR_BGR2LAB).astype(np.float32)

    f_mean = frame_lab.reshape(-1, 3).mean(axis=0)
    f_std = frame_lab.reshape(-1, 3).std(axis=0)
    b_mean = backdrop_lab.reshape(-1, 3).mean(axis=0)
    b_std = backdrop_lab.reshape(-1, 3).std(axis=0)

    # Clip the spread ratio so a flat backdrop (blurred = low variance)
    # can't crush the subject's contrast to nothing.
    ratio = np.clip(b_std / (f_std + 1e-6), 0.6, 1.6)
    matched = (frame_lab - f_mean) * ratio + b_mean

    blended = frame_lab * (1 - amount) + matched * amount
    blended = np.clip(blended, 0, 255).astype(np.uint8)
    return cv2.cvtColor(blended, cv2.COLOR_LAB2BGR)


VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


class BackdropSource:
    """Yields one fitted, pre-blurred backdrop frame per video frame.

    Three interchangeable modes, chosen by what `path` is:
      * None        -> the subject's own room, heavily blurred (privacy)
      * still image -> loaded once, fitted once, reused every frame
      * video file  -> read frame-by-frame and looped when it runs out,
                       so a 10-second street plate covers a 3-minute take
    """

    def __init__(self, path: str | Path | None, blur: int | None) -> None:
        self.still: np.ndarray | None = None
        self.video: cv2.VideoCapture | None = None
        if path is not None:
            if Path(path).suffix.lower() in VIDEO_SUFFIXES:
                self.video = cv2.VideoCapture(str(path))
                if not self.video.isOpened():
                    raise FileNotFoundError(f"Could not open backdrop video: {path}")
            else:
                self.still = cv2.imread(str(path))
                if self.still is None:
                    raise FileNotFoundError(f"Could not read backdrop image: {path}")
        # Heavy blur (31) hides a real room; light blur (9) on a fake
        # backdrop just sells the "portrait mode" depth illusion.
        self.blur = blur if blur is not None else (31 if path is None else 9)
        self._kernel = self.blur * 2 + 1  # blur amount -> odd kernel size
        self._fitted_still: np.ndarray | None = None

    def _blurred(self, image: np.ndarray) -> np.ndarray:
        if self.blur <= 0:
            return image
        return cv2.GaussianBlur(image, (self._kernel, self._kernel), 0)

    def frame_for(self, frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        if self.video is not None:
            ok, plate = self.video.read()
            if not ok:  # plate ended before the take: loop from the top
                self.video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, plate = self.video.read()
                if not ok:
                    raise RuntimeError("Backdrop video has no readable frames")
            return self._blurred(fit_to_frame(plate, width, height))
        if self.still is not None:
            if self._fitted_still is None:  # fit + blur once, reuse forever
                self._fitted_still = self._blurred(fit_to_frame(self.still, width, height))
            return self._fitted_still
        return self._blurred(frame)  # your own room, beyond recognition

    def close(self) -> None:
        if self.video is not None:
            self.video.release()


def process_video(
    src: str | Path,
    dst: str | Path,
    image: str | Path | None = None,
    blur: int | None = None,
    harmonize_amount: float = 0.4,
) -> None:
    """Swap the background for `image` (a photo OR a video plate), or
    blur the real one if no image. See BackdropSource for the modes."""
    segmenter = PersonSegmenter()
    source = BackdropSource(image, blur)
    # Harmonizing toward your own blurred room is a no-op with extra
    # steps — only color-match when there is a foreign backdrop.
    harmonizing = image is not None and harmonize_amount > 0

    def swap_background(frame: np.ndarray) -> np.ndarray:
        bg = source.frame_for(frame)
        if harmonizing:
            frame = harmonize(frame, bg, harmonize_amount)
        mask = feather(segmenter.mask(frame))
        return composite(frame, mask, bg)

    try:
        stream_video(src, dst, swap_background)
    finally:
        segmenter.close()
        source.close()
