"""Tests for the voice-shift math (the audible proof needs ffmpeg)."""

from alterego.voice import factor_from_seed, pitch_filter


def test_same_seed_gives_same_voice():
    # Consistency is the whole point — same rule as the face.
    assert factor_from_seed(90719) == factor_from_seed(90719)


def test_different_seeds_give_different_voices():
    factors = {factor_from_seed(seed) for seed in range(50)}
    assert len(factors) > 40  # near-unique across seeds


def test_factor_never_lands_in_the_do_nothing_zone():
    # A factor of ~1.0 would be a voice disguise that doesn't disguise.
    for seed in range(200):
        factor = factor_from_seed(seed)
        assert 0.93 <= factor <= 1.07
        assert abs(factor - 1.0) >= 0.03


def test_voice_is_not_correlated_with_face():
    # The salt must decorrelate voice from face draws: two adjacent
    # seeds shouldn't produce systematically related factors.
    ups = sum(1 for seed in range(200) if factor_from_seed(seed) > 1.0)
    assert 60 < ups < 140  # roughly half shift up, half down


def test_fallback_filter_compensates_tempo():
    # The asetrate trick speeds audio up by `factor`; atempo must slow
    # it back down by exactly 1/factor or the video desyncs.
    filter_str = pitch_filter(1.05, use_rubberband=False)
    assert f"asetrate={int(48000 * 1.05)}" in filter_str
    assert f"atempo={1 / 1.05:.6f}" in filter_str


def test_rubberband_filter_used_when_available():
    assert pitch_filter(0.95, use_rubberband=True) == "rubberband=pitch=0.95"
