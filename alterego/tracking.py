"""Keep "who is who" stable when several faces share the frame.

The landmark model finds faces but returns them in ARBITRARY order —
frame N's "face 0" is not necessarily frame N-1's "face 0". If the
order flips for even one frame, person A's jaw lands on person B: a
visible glitch and an identity leak. Two small machines fix it:

  * CentroidTracker — frame-to-frame continuity. Each detection
    inherits the ID of the nearest track from the previous frame
    (within a radius scaled by face size, so a webcam close-up and a
    wide shot both work). Tracks survive brief misses; a face that
    vanishes long enough is retired.

  * SlotAssigner — identity slots on top of track IDs. Slot 0 = the
    first --identity on the command line, slot 1 the next, etc. New
    tracks claim the lowest free slot (simultaneous newcomers are
    ordered left-to-right, the natural reading of a two-shot). When
    a track dies its slot frees, so someone stepping out and back
    into frame gets their identity back.

Honest limits, documented on purpose: if two people fully cross or
swap seats while BOTH are lost to the tracker, their identities can
swap — position is our only cue. Face-embedding re-identification is
the known fix and belongs to a future phase; for seated formats
(podcasts, interviews, multi-persona solo shoots) position is enough.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def face_width_of(landmarks: np.ndarray) -> float:
    """Cheek-to-cheek width — the scale used to judge 'near'."""
    return float(np.linalg.norm(landmarks[454] - landmarks[234]))


@dataclass
class Track:
    track_id: int
    landmarks: np.ndarray
    missed: int = 0

    @property
    def centroid(self) -> np.ndarray:
        return self.landmarks.mean(axis=0)


@dataclass
class CentroidTracker:
    """Greedy nearest-centroid matching with miss tolerance."""

    max_missed: int = 30          # frames a track survives unseen (~1-2 s)
    match_radius_faces: float = 1.5  # "near" = within 1.5 face-widths

    _tracks: dict[int, Track] = field(default_factory=dict)
    _next_id: int = 0

    def update(self, detections: list[np.ndarray]) -> dict[int, np.ndarray]:
        """Feed one frame's detections; get {track_id: landmarks} back."""
        # Score every (track, detection) pair by centroid distance,
        # then greedily take the closest pairs first. With 2-4 faces
        # this is a handful of comparisons — no Hungarian needed.
        pairs: list[tuple[float, int, int]] = []
        for track_id, track in self._tracks.items():
            for det_index, det in enumerate(detections):
                distance = float(np.linalg.norm(track.centroid - det.mean(axis=0)))
                pairs.append((distance, track_id, det_index))
        pairs.sort()

        matched_tracks: set[int] = set()
        matched_dets: set[int] = set()
        for distance, track_id, det_index in pairs:
            if track_id in matched_tracks or det_index in matched_dets:
                continue
            radius = self.match_radius_faces * face_width_of(detections[det_index])
            if distance > radius:
                continue  # too far to be the same person
            track = self._tracks[track_id]
            track.landmarks = detections[det_index]
            track.missed = 0
            matched_tracks.add(track_id)
            matched_dets.add(det_index)

        # Unmatched detections are new people entering the frame.
        # Sort left-to-right so simultaneous entries get stable order.
        newcomers = sorted(
            (det for i, det in enumerate(detections) if i not in matched_dets),
            key=lambda det: float(det.mean(axis=0)[0]),
        )
        for det in newcomers:
            self._tracks[self._next_id] = Track(self._next_id, det)
            matched_tracks.add(self._next_id)
            self._next_id += 1

        # Unmatched tracks age; the forgotten are retired.
        for track_id in list(self._tracks):
            if track_id not in matched_tracks:
                self._tracks[track_id].missed += 1
                if self._tracks[track_id].missed > self.max_missed:
                    del self._tracks[track_id]

        # Only tracks SEEN THIS FRAME get warped — a track coasting on
        # misses has stale landmarks, and warping with those smears.
        return {
            tid: t.landmarks
            for tid, t in self._tracks.items()
            if t.missed == 0 and tid in matched_tracks
        }

    def active_ids(self) -> set[int]:
        return set(self._tracks)


@dataclass
class SlotAssigner:
    """Map track IDs to identity slots (0 = first --identity, ...)."""

    n_slots: int
    _slot_of: dict[int, int] = field(default_factory=dict)

    def assign(
        self, visible: dict[int, np.ndarray], alive: set[int]
    ) -> dict[int, int]:
        """Returns {track_id: slot} for visible tracks that own a slot."""
        # Free the slots of tracks that no longer exist at all.
        for track_id in list(self._slot_of):
            if track_id not in alive:
                del self._slot_of[track_id]

        taken = set(self._slot_of.values())
        free = [s for s in range(self.n_slots) if s not in taken]

        # Unassigned visible tracks claim free slots, left-to-right.
        unassigned = sorted(
            (tid for tid in visible if tid not in self._slot_of),
            key=lambda tid: float(visible[tid].mean(axis=0)[0]),
        )
        for track_id in unassigned:
            if not free:
                break  # more faces than identities: extras stay unwarped
            self._slot_of[track_id] = free.pop(0)

        return {tid: s for tid, s in self._slot_of.items() if tid in visible}
