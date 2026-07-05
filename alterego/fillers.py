"""Find filler words ("um", "uh"...) so the cutter can remove them.

Silence removal (cuts.py) handles the gaps BETWEEN sentences; fillers
are the noise INSIDE them. Finding a filler requires knowing what was
said and exactly when — so this module runs speech recognition with
word-level timestamps and returns the time ranges of filler words.
The actual cutting stays in cuts.py: fillers are just more ranges.

We use faster-whisper's `tiny` model, quantized to int8: ~75 MB on
disk, runs in well under 1 GB of RAM — chosen specifically to fit a
4 GB machine. Bigger models transcribe *meaning* better, but filler
detection only needs the easy words, so tiny is genuinely enough.

This is the one optional dependency in the project. Install it with:
    uv sync --extra speech
"""

from __future__ import annotations

from pathlib import Path

Word = tuple[str, float, float]  # (text, start_seconds, end_seconds)
Segment = tuple[float, float]

# Conservative by default: only sounds that are ALWAYS filler.
# Words like "like" or "so" are sometimes filler, sometimes meaning —
# cutting those automatically would mangle real sentences, so they're
# opt-in via --also-cut.
FILLER_WORDS = {"um", "uh", "uhm", "erm", "hmm", "mmm", "er", "ehm"}


def _normalize(word: str) -> str:
    """Whisper attaches punctuation to words (' Um,') — strip it so
    dictionary lookup works."""
    return word.strip().lower().strip(".,!?;:—-\"'")


def transcribe_words(video: str | Path) -> list[Word]:
    """Run speech-to-text and return every word with its time range."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit(
            "Filler removal needs the speech extra. Run: uv sync --extra speech"
        )

    # int8 = 8-bit quantized weights: 4x less RAM than float32 for a
    # barely measurable accuracy cost. First run downloads the model.
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(video), word_timestamps=True)

    words: list[Word] = []
    for segment in segments:  # segments is a generator: streams, low RAM
        for word in segment.words or []:
            # Keep whisper's RAW text (casing, punctuation, the leading
            # space) — captions need it verbatim; filler matching
            # normalizes its own copy at comparison time.
            words.append((word.word, word.start, word.end))
    return words


def filler_ranges(
    words: list[Word],
    also_cut: tuple[str, ...] = (),
    padding: float = 0.04,
) -> list[Segment]:
    """Time ranges of every filler word, slightly padded.

    The padding (40 ms) swallows the breathy edges of the filler that
    whisper's timestamps tend to miss; without it a ghost of the "um"
    survives the cut.
    """
    targets = FILLER_WORDS | {_normalize(w) for w in also_cut}
    return [
        (max(start - padding, 0.0), end + padding)
        for text, start, end in words
        if _normalize(text) in targets
    ]
