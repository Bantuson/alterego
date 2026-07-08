"""Tests for live-mode routing — above all, the fail-closed guarantee.

The heavy models are injected as fakes, so these tests verify the
DECISIONS (when to warp, when to hide, when to rebuild) without a
camera. That separation is why the pipeline accepts its components
as constructor arguments.
"""

import numpy as np

from alterego.live import (
    LivePipeline,
    build_tone_lut,
    landmarks_moved,
    pixelate_region,
)


class FakeLandmarker:
    """Returns a scripted sequence of detections (None = face lost)."""

    def __init__(self, script):
        self.script = list(script)

    def detect(self, _frame):
        return self.script.pop(0) if self.script else None

    def close(self):
        pass


class FakeSegmenter:
    """Always finds a person filling the middle of the frame."""

    def mask(self, frame):
        mask = np.zeros(frame.shape[:2], np.float32)
        mask[10:-10, 10:-10] = 1.0
        return mask

    def close(self):
        pass


def face_landmarks(offset=0.0):
    rng = np.random.default_rng(0)
    return rng.uniform(100, 200, size=(478, 2)) + offset


def make_pipeline(script):
    from alterego.disguise import DisguiseProfile

    return LivePipeline(
        profile=DisguiseProfile.from_seed(1),
        landmarker=FakeLandmarker(script), segmenter=FakeSegmenter(),
        grace_frames=1,
    )


def frame():
    return np.full((240, 320, 3), 128, np.uint8)


def test_detected_face_is_warped_and_reported_protected():
    pipeline = make_pipeline([face_landmarks()])
    _out, protected = pipeline.process(frame())
    assert protected


def test_lost_face_fails_closed_after_grace():
    # grace_frames=1: first miss is tolerated (but still hidden),
    # second miss is the hard fail-closed path. NEITHER may be
    # reported as protected.
    pipeline = make_pipeline([face_landmarks(), None, None])
    pipeline.process(frame())
    _out, protected_first_miss = pipeline.process(frame())
    _out, protected_second_miss = pipeline.process(frame())
    assert not protected_first_miss
    assert not protected_second_miss


def test_unprotected_frames_are_visibly_hidden():
    pipeline = make_pipeline([None, None])
    original = frame()
    # Give the frame texture so pixelation is measurable.
    original[::2] = 30
    out, protected = pipeline.process(original.copy())
    assert not protected
    # The person region (mask center) must differ from the original.
    assert np.abs(out[100:140, 100:220].astype(int) - original[100:140, 100:220]).mean() > 5


def test_pixelate_without_mask_hides_everything():
    textured = np.zeros((64, 64, 3), np.uint8)
    textured[::2] = 200
    out = pixelate_region(textured, mask=None, block=16)
    # Mosaic averages the stripes away: variance collapses.
    assert out.std() < textured.std() / 2


def test_landmarks_moved_ignores_jitter_but_sees_movement():
    base = face_landmarks()
    assert not landmarks_moved(base, base + 0.5)  # sub-threshold jitter
    assert landmarks_moved(base, base + 5.0)  # real movement
    assert landmarks_moved(None, base)  # first frame always builds


def test_tone_lut_lifts_shadows_without_clipping_highlights():
    lut = build_tone_lut()
    assert lut[30] > 30  # shadows lifted
    assert lut[255] <= 255 and lut[0] == 0  # endpoints sane
    assert np.all(np.diff(lut.astype(int)) >= 0)  # monotonic: no banding
