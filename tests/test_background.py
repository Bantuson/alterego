"""Tests for the compositing math (the model itself needs real footage)."""

import cv2
import numpy as np

from alterego.background import BackdropSource, composite, fit_to_frame, harmonize


def test_mask_one_keeps_the_person():
    person = np.full((4, 4, 3), 200, np.uint8)
    backdrop = np.full((4, 4, 3), 10, np.uint8)
    mask = np.ones((4, 4), np.float32)
    assert np.array_equal(composite(person, mask, backdrop), person)


def test_mask_zero_shows_the_backdrop():
    person = np.full((4, 4, 3), 200, np.uint8)
    backdrop = np.full((4, 4, 3), 10, np.uint8)
    mask = np.zeros((4, 4), np.float32)
    assert np.array_equal(composite(person, mask, backdrop), backdrop)


def test_half_mask_blends_halfway():
    person = np.full((4, 4, 3), 200, np.uint8)
    backdrop = np.full((4, 4, 3), 100, np.uint8)
    mask = np.full((4, 4), 0.5, np.float32)
    assert np.allclose(composite(person, mask, backdrop), 150, atol=1)


def test_fit_to_frame_returns_exact_size_without_stretching():
    # A wide panorama fitted into a 4:3 frame must be center-cropped,
    # not squashed.
    panorama = np.zeros((100, 400, 3), np.uint8)
    fitted = fit_to_frame(panorama, width=200, height=150)
    assert fitted.shape == (150, 200, 3)


def _noisy(mean_bgr, seed):
    """A flat-color image with noise, so it has non-zero std for
    harmonize's spread-matching to work with."""
    rng = np.random.default_rng(seed)
    base = np.full((40, 40, 3), mean_bgr, np.float32)
    return np.clip(base + rng.normal(0, 12, base.shape), 0, 255).astype(np.uint8)


def test_harmonize_pulls_subject_toward_backdrop_tones():
    warm_subject = _noisy((40, 90, 200), seed=1)  # BGR: reddish
    cool_backdrop = _noisy((200, 120, 40), seed=2)  # BGR: bluish
    result = harmonize(warm_subject, cool_backdrop, amount=1.0)
    # After a full transfer the subject's mean color should be much
    # closer to the backdrop's than it started.
    before = np.abs(warm_subject.mean((0, 1)) - cool_backdrop.mean((0, 1))).sum()
    after = np.abs(result.mean((0, 1)) - cool_backdrop.mean((0, 1))).sum()
    assert after < before * 0.5


def test_harmonize_amount_zero_is_identity():
    frame = _noisy((100, 100, 100), seed=3)
    assert np.array_equal(harmonize(frame, _noisy((0, 0, 255), 4), amount=0.0), frame)


def test_backdrop_source_loops_a_video_plate(tmp_path):
    # A 3-frame plate must serve a 7-frame take by wrapping around.
    plate_path = str(tmp_path / "plate.mp4")
    writer = cv2.VideoWriter(plate_path, cv2.VideoWriter_fourcc(*"mp4v"), 30, (32, 32))
    for value in (50, 100, 150):  # frame brightness encodes frame index
        writer.write(np.full((32, 32, 3), value, np.uint8))
    writer.release()

    source = BackdropSource(plate_path, blur=0)
    take_frame = np.zeros((32, 32, 3), np.uint8)
    values = [int(source.frame_for(take_frame).mean()) for _ in range(7)]
    source.close()
    # 7 requests over a 3-frame plate: the pattern must repeat with
    # period 3 (allow a little codec wiggle) and actually cycle.
    assert abs(values[3] - values[0]) < 5
    assert abs(values[6] - values[0]) < 5
    assert max(values) - min(values) > 50
