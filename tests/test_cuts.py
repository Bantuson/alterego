"""Tests for the interval arithmetic behind silence cutting."""

import pytest

from alterego.cuts import keep_segments


def test_no_silences_keeps_everything():
    assert keep_segments([], duration=10.0) == [(0.0, 10.0)]


def test_one_middle_silence_splits_into_two_segments():
    segments = keep_segments([(4.0, 6.0)], duration=10.0, padding=0.0)
    assert segments == [(0.0, 4.0), (6.0, 10.0)]


def test_padding_keeps_a_beat_of_quiet_around_each_cut():
    segments = keep_segments([(4.0, 6.0)], duration=10.0, padding=0.5)
    # Speech ends at 4.0 but we keep until 4.5; resume at 5.5 not 6.0.
    assert segments == [(0.0, 4.5), (5.5, 10.0)]


def test_silence_at_the_very_start_is_dropped():
    segments = keep_segments([(0.0, 3.0)], duration=10.0, padding=0.0)
    assert segments == [(3.0, 10.0)]


def test_silence_running_to_the_end_is_dropped():
    segments = keep_segments([(7.0, 10.0)], duration=10.0, padding=0.0)
    assert segments == [(0.0, 7.0)]


def test_kept_time_never_exceeds_duration():
    silences = [(1.0, 2.0), (3.0, 5.0), (8.0, 9.0)]
    segments = keep_segments(silences, duration=10.0, padding=0.2)
    kept = sum(end - start for start, end in segments)
    assert kept <= 10.0
    # Segments must be in order and non-overlapping.
    for (_, prev_end), (next_start, _) in zip(segments, segments[1:]):
        assert next_start >= prev_end
