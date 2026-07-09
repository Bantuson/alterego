"""Tests for multi-face tracking — the 'who is who' guarantees.

Faces are simulated as landmark clouds around a moving center. The
scenarios are the ways multi-person shots actually break: the model
returning faces in a different order, a person blinking out for a few
frames, someone leaving and coming back, and a third face appearing
when only two identities exist.
"""

import numpy as np

from alterego.tracking import CentroidTracker, SlotAssigner


def face_at(x: float, y: float = 200.0, size: float = 80.0) -> np.ndarray:
    """A fake 478-point face centered at (x, y).

    The tracker measures scale as the distance between landmarks 454
    and 234 (the cheeks), so those two are placed deliberately.
    """
    rng = np.random.default_rng(0)
    cloud = rng.uniform(-size / 2, size / 2, (478, 2)) + (x, y)
    cloud[454] = (x + size / 2, y)
    cloud[234] = (x - size / 2, y)
    return cloud


def test_detection_order_flip_does_not_swap_tracks():
    tracker = CentroidTracker()
    tracker.update([face_at(100), face_at(500)])
    first = tracker.update([face_at(102), face_at(498)])
    # Same people, detections delivered in REVERSED order:
    flipped = tracker.update([face_at(496), face_at(104)])
    ids_by_x_first = sorted(first, key=lambda t: first[t].mean(0)[0])
    ids_by_x_flipped = sorted(flipped, key=lambda t: flipped[t].mean(0)[0])
    assert ids_by_x_first == ids_by_x_flipped  # left person kept their ID


def test_track_survives_brief_disappearance():
    tracker = CentroidTracker(max_missed=5)
    (only_id,) = tracker.update([face_at(300)])
    for _ in range(3):  # face lost for 3 frames (within tolerance)
        tracker.update([])
    (returned_id,) = tracker.update([face_at(310)])
    assert returned_id == only_id


def test_long_gone_track_is_retired():
    tracker = CentroidTracker(max_missed=2)
    (old_id,) = tracker.update([face_at(300)])
    for _ in range(5):  # gone way past tolerance
        tracker.update([])
    (new_id,) = tracker.update([face_at(300)])
    assert new_id != old_id


def test_moved_too_far_is_a_new_person_not_a_teleport():
    tracker = CentroidTracker()
    tracker.update([face_at(100)])
    visible = tracker.update([face_at(900)])  # 10 face-widths away
    assert len(tracker.active_ids()) == 2  # old track aging, new track made
    assert len(visible) == 1


def test_slots_assign_left_to_right_and_return_after_absence():
    tracker = CentroidTracker(max_missed=3)
    assigner = SlotAssigner(n_slots=2)

    visible = tracker.update([face_at(500), face_at(100)])  # right listed first
    slots = assigner.assign(visible, tracker.active_ids())
    by_slot = {s: visible[t].mean(0)[0] for t, s in slots.items()}
    assert by_slot[0] < by_slot[1]  # slot 0 = leftmost, regardless of order

    # Left person steps out briefly; slot 0 must NOT be reassigned...
    visible = tracker.update([face_at(505)])
    slots = assigner.assign(visible, tracker.active_ids())
    assert list(slots.values()) == [1]
    # ...and they get slot 0 back on return.
    visible = tracker.update([face_at(110), face_at(505)])
    slots = assigner.assign(visible, tracker.active_ids())
    by_slot = {s: visible[t].mean(0)[0] for t, s in slots.items()}
    assert by_slot[0] < by_slot[1]


def test_more_faces_than_identities_leaves_extras_unassigned():
    tracker = CentroidTracker()
    assigner = SlotAssigner(n_slots=2)
    visible = tracker.update([face_at(100), face_at(400), face_at(700)])
    slots = assigner.assign(visible, tracker.active_ids())
    assert len(slots) == 2  # third face wears no identity (and post warns)
