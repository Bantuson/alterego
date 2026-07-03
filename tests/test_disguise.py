"""Tests for the disguise math — the parts we can verify without a webcam.

Lesson worth stealing: structure code so the *logic* (pure functions on
arrays) is separate from the *I/O* (cameras, files). Then the logic is
testable in milliseconds, and the I/O is thin enough to trust.
"""

import numpy as np
import pytest

from alterego.disguise import DisguiseProfile, control_shifts, displacement_field


def fake_landmarks() -> np.ndarray:
    """A synthetic 468-point face: random points in a 200px box centered
    at (320, 240). Not anatomically real — the math only needs positions."""
    rng = np.random.default_rng(0)
    return rng.uniform(220, 420, size=(468, 2))


def test_same_seed_gives_same_alter_ego():
    # The whole privacy promise rests on this: one seed, one face.
    assert DisguiseProfile.from_seed(42) == DisguiseProfile.from_seed(42)


def test_different_seeds_give_different_alter_egos():
    assert DisguiseProfile.from_seed(1) != DisguiseProfile.from_seed(2)


def test_strength_scales_the_profile():
    full = DisguiseProfile.from_seed(7, strength=1.0)
    half = DisguiseProfile.from_seed(7, strength=0.5)
    assert half.jaw_width == pytest.approx(full.jaw_width * 0.5)


def test_zero_strength_means_no_shifts():
    profile = DisguiseProfile.from_seed(9, strength=0.0)
    _, shifts = control_shifts(fake_landmarks(), profile)
    assert np.allclose(shifts, 0)


def test_shifts_are_a_small_fraction_of_face_size():
    # "Naturally different" depends on subtlety: no single feature may
    # move more than ~6% of face width even at full strength.
    landmarks = fake_landmarks()
    points, shifts = control_shifts(landmarks, DisguiseProfile.from_seed(3))
    face_width = np.linalg.norm(landmarks[454] - landmarks[234])
    assert np.abs(shifts).max() <= 0.06 * face_width


def test_field_peaks_at_control_point_and_fades_out():
    points = np.array([[100.0, 100.0]], dtype=np.float32)
    shifts = np.array([[10.0, 0.0]], dtype=np.float32)
    field_x, _ = displacement_field((200, 200), points, shifts, sigma=20)

    at_point = field_x[100, 100]
    far_away = field_x[10, 190]
    assert at_point == pytest.approx(10.0, abs=1.0)  # full shift at the point
    assert abs(far_away) < 0.5  # effect has died off far away
