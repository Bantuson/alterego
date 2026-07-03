"""Tests for the compositing math (the model itself needs real footage)."""

import numpy as np

from alterego.background import composite, fit_to_frame


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
