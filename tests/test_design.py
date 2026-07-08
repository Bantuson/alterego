"""Tests for reference matching — geometry we can construct by hand."""

import numpy as np

from alterego.design import KNOB_GAIN, knobs_from_reference, measure_ratios
from alterego.disguise import POINT


def synthetic_face(jaw=0.9, eyes=0.30, mouth=0.45) -> np.ndarray:
    """Build a 478-landmark array where only the points we measure
    are meaningful, placed to produce KNOWN ratios."""
    landmarks = np.zeros((478, 2))
    width = 200.0  # cheek-to-cheek pixels

    def put(name, x, y):
        landmarks[POINT[name]] = (x, y)

    put("cheek_right", 0, 100)
    put("cheek_left", width, 100)
    put("jaw_right", width * (0.5 - jaw / 2), 160)
    put("jaw_left", width * (0.5 + jaw / 2), 160)
    put("eye_inner_right", width * (0.5 - eyes / 2), 80)
    put("eye_inner_left", width * (0.5 + eyes / 2), 80)
    put("eye_outer_right", 40, 80)
    put("eye_outer_left", 160, 80)
    put("brow_right", 40, 60)
    put("brow_left", 160, 60)
    put("nose_bridge", 100, 80)
    put("nose_tip", 100, 130)
    put("nostril_right", 85, 135)
    put("nostril_left", 115, 135)
    put("mouth_right", width * (0.5 - mouth / 2), 165)
    put("mouth_left", width * (0.5 + mouth / 2), 165)
    put("lip_top", 100, 160)
    put("lip_bottom", 100, 172)
    put("chin", 100, 195)
    return landmarks


def test_ratios_are_scale_invariant():
    # The same face photographed closer (2x bigger) must measure identically.
    near = measure_ratios(synthetic_face() * 2.0)
    far = measure_ratios(synthetic_face())
    for name in near:
        assert abs(near[name] - far[name]) < 1e-9


def test_measured_ratios_match_construction():
    ratios = measure_ratios(synthetic_face(jaw=0.9, eyes=0.30, mouth=0.45))
    assert abs(ratios["jaw_width"] - 0.9) < 1e-9
    assert abs(ratios["eye_spacing"] - 0.30) < 1e-9
    assert abs(ratios["mouth_width"] - 0.45) < 1e-9


def test_reference_with_wider_jaw_pushes_jaw_knob_positive():
    mine = measure_ratios(synthetic_face(jaw=0.85))
    target = measure_ratios(synthetic_face(jaw=0.90))
    profile = knobs_from_reference(mine, target)
    assert profile.jaw_width > 0
    # ...and an identical reference asks for no change at all.
    same = knobs_from_reference(mine, mine)
    assert all(abs(v) < 1e-9 for v in same.to_dict().values())


def test_extreme_references_are_clamped_to_the_naturalness_budget():
    mine = measure_ratios(synthetic_face(jaw=0.6, eyes=0.2))
    target = measure_ratios(synthetic_face(jaw=1.2, eyes=0.5))  # cartoonishly far
    profile = knobs_from_reference(mine, target)
    for value in profile.to_dict().values():
        assert -1.0 <= value <= 1.0


def test_gain_table_covers_every_knob():
    from dataclasses import fields

    from alterego.disguise import DisguiseProfile

    assert set(KNOB_GAIN) == {f.name for f in fields(DisguiseProfile)}
