"""Tests for filler detection logic and range merging (no model needed)."""

import pytest

from alterego.cuts import merge_ranges
from alterego.fillers import filler_ranges


def test_fillers_are_found_despite_whisper_punctuation():
    # Whisper emits RAW words like " Um," (leading space, casing,
    # punctuation) — filler matching must normalize its own copy.
    words = [(" Um,", 1.0, 1.3), (" hello", 1.4, 1.8), (" uh...", 2.0, 2.2)]
    ranges = filler_ranges(words, padding=0.0)
    assert ranges == [(1.0, 1.3), (2.0, 2.2)]


def test_meaning_words_survive_by_default():
    # "like" is only cut when explicitly opted in.
    words = [("like", 1.0, 1.2), ("um", 2.0, 2.1)]
    assert len(filler_ranges(words)) == 1
    assert len(filler_ranges(words, also_cut=("like",))) == 2


def test_padding_expands_but_never_goes_negative():
    ranges = filler_ranges([("um", 0.01, 0.3)], padding=0.05)
    assert ranges[0][0] == 0.0
    assert ranges[0][1] == pytest.approx(0.35)


def test_merge_ranges_fuses_overlaps():
    ranges = [(5.0, 6.0), (1.0, 2.0), (1.5, 3.0)]
    assert merge_ranges(ranges) == [(1.0, 3.0), (5.0, 6.0)]


def test_merge_ranges_keeps_disjoint_ranges_apart():
    ranges = [(1.0, 2.0), (3.0, 4.0)]
    assert merge_ranges(ranges) == [(1.0, 2.0), (3.0, 4.0)]
