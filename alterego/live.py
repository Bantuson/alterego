"""Real-time disguise + background + grade: the live alter ego.

The post pipeline optimizes for QUALITY (every frame gets the full
treatment). Live mode optimizes for a DEADLINE: at 15 fps each frame
has a 66 ms budget, spent across detection, warping, segmentation,
compositing, and grading. Three observations buy back most of it:

  1. Bodies barely move in 100 ms -> run person segmentation every
     Nth frame and reuse the mask.
  2. The face warp barely changes between frames -> rebuild the warp
     maps only when landmarks actually moved; replaying cached maps
     is one cheap cv2.remap call.
  3. Studio grading (CLAHE) is too slow live -> precompute a tone
     curve as a 256-entry lookup table; apply in ~1 ms.

THE SAFETY RULE — fail closed:
In post, a frame with no detected face passes through untouched and
you review it before publishing. Live, that same frame would leak
your REAL face to the audience, unreviewably. So when landmarks drop,
the person region gets pixelated (segmentation keeps working in
conditions where landmarks fail — we measured this) and the frame is
flagged. Never passthrough. The same rule lives in live_voice.py.
"""

from __future__ import annotations

import threading
import time

import cv2
import numpy as np

from .background import BackdropSource, PersonSegmenter, composite, feather
from .disguise import DisguiseProfile, control_shifts, displacement_field
from .faces import FaceLandmarker, LandmarkSmoother

# How far (in pixels, on average) landmarks must move before the warp
# maps are rebuilt. Below this, detection jitter is the likely cause
# and the cached warp is MORE stable than a fresh one.
REBUILD_THRESHOLD_PX = 1.5


def landmarks_moved(
    previous: np.ndarray | None, current: np.ndarray, threshold: float = REBUILD_THRESHOLD_PX
) -> bool:
    """Decide whether the face moved enough to justify a rebuild."""
    if previous is None or previous.shape != current.shape:
        return True
    return float(np.abs(current - previous).mean()) > threshold


def pixelate_region(frame: np.ndarray, mask: np.ndarray | None, block: int = 24) -> np.ndarray:
    """The fail-closed frame: mosaic the person (or everything).

    Pixelation beats Gaussian blur here: it is unmistakably deliberate
    (viewers read it as censorship, not a broken camera) and it is
    cheap — downscale then upscale with nearest-neighbor.
    """
    height, width = frame.shape[:2]
    small = cv2.resize(frame, (max(1, width // block), max(1, height // block)))
    mosaic = cv2.resize(small, (width, height), interpolation=cv2.INTER_NEAREST)
    if mask is None:
        return mosaic  # no segmentation either: hide the whole frame
    return composite(mosaic, mask, frame)  # mosaic where the person is


def build_tone_lut(gamma: float = 1.15, contrast: float = 1.06) -> np.ndarray:
    """Precompute the live color grade as a lookup table.

    A gentle gamma lift plus an s-curve around the midpoint — the
    2-cent version of the post pipeline's grade, but it costs one
    table lookup per pixel instead of a CLAHE pass.
    """
    x = np.arange(256, dtype=np.float32) / 255.0
    x = x ** (1.0 / gamma)
    x = (x - 0.5) * contrast + 0.5
    return (np.clip(x, 0, 1) * 255).astype(np.uint8)


class FrameGrabber:
    """Reads the camera on its own thread; the pipeline never waits.

    cv2's read() BLOCKS until the sensor delivers — ~34 ms at 30 fps,
    100 ms in low light. On one thread that wait is added to every
    frame's budget. On its own thread the camera fills a "latest
    frame" slot while the pipeline works, and if processing falls
    behind, stale frames are simply overwritten — for live video,
    dropping old frames IS the correct behavior (live means now).
    """

    def __init__(self, capture: cv2.VideoCapture) -> None:
        self._capture = capture
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while self._running:
            ok, frame = self._capture.read()
            if not ok:
                self._running = False
                return
            with self._lock:
                self._frame = frame

    def read(self) -> np.ndarray | None:
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    @property
    def alive(self) -> bool:
        return self._running

    def stop(self) -> None:
        self._running = False
        self._thread.join(timeout=2)


class CachedDisguise:
    """The face warp with observation #2 applied: rebuild rarely."""

    def __init__(self, profile: DisguiseProfile) -> None:
        self.profile = profile
        self._maps: tuple[np.ndarray, np.ndarray] | None = None
        self._anchor: np.ndarray | None = None

    def apply(self, frame: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
        if self._maps is None or landmarks_moved(self._anchor, landmarks):
            points, shifts = control_shifts(landmarks, self.profile)
            face_width = np.linalg.norm(landmarks[454] - landmarks[234])
            field_x, field_y = displacement_field(
                frame.shape[:2], points, -shifts, sigma=face_width * 0.18
            )
            height, width = frame.shape[:2]
            grid_x, grid_y = np.meshgrid(
                np.arange(width, dtype=np.float32),
                np.arange(height, dtype=np.float32),
            )
            self._maps = (grid_x + field_x, grid_y + field_y)
            self._anchor = landmarks
        return cv2.remap(
            frame, self._maps[0], self._maps[1],
            interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT,
        )


class LivePipeline:
    """One frame in, one protected frame out, on a deadline.

    The heavy components are injectable for testing — tests pass fakes
    that return known landmarks/masks, so the routing logic (including
    fail-closed) is verifiable without a camera or the real models.
    """

    def __init__(
        self,
        profile: DisguiseProfile,
        backdrop: str | None = None,
        seg_every: int = 3,
        grace_frames: int = 3,
        landmarker=None,
        segmenter=None,
    ) -> None:
        self.disguise = CachedDisguise(profile)
        self.landmarker = landmarker or FaceLandmarker()
        self.segmenter = segmenter or PersonSegmenter()
        self.smoother = LandmarkSmoother()
        self.backdrop = BackdropSource(backdrop, blur=None) if backdrop else None
        self.seg_every = seg_every
        # Detection blips one frame long shouldn't nuke the stream;
        # `grace_frames` of leniency, then fail closed.
        self.grace_frames = grace_frames
        self._grace = grace_frames
        self._mask: np.ndarray | None = None
        self._tick = 0
        self._lut = build_tone_lut()

    def process(self, frame: np.ndarray) -> tuple[np.ndarray, bool]:
        """Returns (frame, protected) — protected=False means the face
        was not warped and the fail-closed path fired instead."""
        self._tick += 1

        # Observation #1: refresh the person mask every Nth frame only.
        if self._mask is None or self._tick % self.seg_every == 0:
            self._mask = feather(self.segmenter.mask(frame))

        landmarks = self.smoother.update(self.landmarker.detect(frame))

        if landmarks is None:
            self._grace -= 1
            if self._grace < 0:
                # FAIL CLOSED: no landmarks -> mosaic the person.
                out = pixelate_region(frame, self._mask)
                out = cv2.LUT(out, self._lut)
                return out, False
            # Inside the grace window: frame is dropped from disguise
            # but we still hide the person rather than show them raw.
            out = pixelate_region(frame, self._mask)
            return cv2.LUT(out, self._lut), False

        self._grace = self.grace_frames
        out = self.disguise.apply(frame, landmarks)
        if self.backdrop is not None:
            out = composite(out, self._mask, self.backdrop.frame_for(out))
        return cv2.LUT(out, self._lut), True

    def close(self) -> None:
        self.landmarker.close()
        self.segmenter.close()
        if self.backdrop is not None:
            self.backdrop.close()


def run_live(
    profile: DisguiseProfile,
    backdrop: str | None = None,
    camera_index: int = 0,
    width: int = 640,
    window: bool = False,
    max_frames: int | None = None,
) -> None:
    """Capture -> protect -> virtual camera (or preview window).

    The virtual camera route needs OBS installed once (its driver
    provides the device). Without it — or with `window=True` — frames
    go to a preview window instead, which is also how you rehearse.
    """
    capture = cv2.VideoCapture(camera_index)
    if not capture.isOpened():
        raise SystemExit(f"No webcam at index {camera_index}.")

    ok, first = capture.read()
    if not ok:
        raise SystemExit("Webcam opened but produced no frames.")
    scale = width / first.shape[1]
    height = int(first.shape[0] * scale)

    pipeline = LivePipeline(profile, backdrop)

    virtual_cam = None
    if not window:
        try:
            import pyvirtualcam

            virtual_cam = pyvirtualcam.Camera(
                width=width, height=height, fps=20, fmt=pyvirtualcam.PixelFormat.BGR
            )
            print(f"● live -> virtual camera '{virtual_cam.device}' — Ctrl+C to stop")
        except Exception as error:
            print(f"No virtual camera ({error}); falling back to a preview window.")
            print("For streaming: install OBS once, then run again.")
    if virtual_cam is None:
        print("● live preview — press Q in the window to stop")

    grabber = FrameGrabber(capture)
    frames = 0
    protected_count = 0
    started = time.time()
    try:
        while grabber.alive:
            frame = grabber.read()
            if frame is None:
                time.sleep(0.005)  # camera warming up
                continue
            frame = cv2.resize(frame, (width, height))
            out, protected = pipeline.process(frame)
            protected_count += int(protected)
            frames += 1

            if virtual_cam is not None:
                virtual_cam.send(out)
                virtual_cam.sleep_until_next_frame()
            else:
                cv2.imshow("alterego live", out)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            if frames % 60 == 0:
                fps = frames / (time.time() - started)
                print(f"  {fps:.1f} fps | disguise coverage {protected_count / frames:.0%}")
            if max_frames is not None and frames >= max_frames:
                break
    except KeyboardInterrupt:
        pass
    finally:
        # Stop the clock BEFORE cleanup: model teardown can take
        # seconds and would corrupt the fps figure (it did — the
        # summary once reported 4.6 fps for a 20 fps session).
        elapsed = time.time() - started
        grabber.stop()
        capture.release()
        if virtual_cam is not None:
            virtual_cam.close()
        cv2.destroyAllWindows()
        pipeline.close()

    if frames:
        fps = frames / elapsed
        print(
            f"\n{frames} frames at {fps:.1f} fps — "
            f"disguise covered {protected_count / frames:.0%}, "
            f"fail-closed covered the rest."
        )
