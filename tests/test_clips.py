"""Tests for the caption-format conversion (Python↔Remotion contract)."""

from alterego.clips import words_to_captions


def test_seconds_become_milliseconds():
    captions = words_to_captions([(" Hello", 1.5, 2.25)])
    assert captions[0]["startMs"] == 1500
    assert captions[0]["endMs"] == 2250
    assert captions[0]["timestampMs"] == 1875  # midpoint


def test_raw_whisper_text_kept_verbatim():
    # Caption layout is whitespace-sensitive: the leading space and
    # punctuation whisper produces must survive untouched.
    captions = words_to_captions([(" Um,", 0.0, 0.4)])
    assert captions[0]["text"] == " Um,"


def test_caption_shape_matches_remotion_contract():
    (caption,) = words_to_captions([(" word", 0.0, 1.0)])
    assert set(caption) == {"text", "startMs", "endMs", "timestampMs", "confidence"}
