"""Tests for the real-time pitch shifter — pure math, no audio device.

The shifter is a pure function of numpy blocks, so we can verify it
the same way we verified the offline voice stage: synthesize a tone,
shift it, measure the frequency that comes out.
"""

import numpy as np

from alterego.live_voice import PitchShifter

SAMPLERATE = 44100


def run_through(shifter: PitchShifter, signal: np.ndarray, blocksize: int = 1024) -> np.ndarray:
    """Feed a signal through in live-sized blocks, like a mic would."""
    blocks = [
        shifter.process(signal[i : i + blocksize])
        for i in range(0, len(signal) - blocksize, blocksize)
    ]
    return np.concatenate(blocks)


def sine(freq: float, seconds: float = 2.0) -> np.ndarray:
    t = np.arange(int(SAMPLERATE * seconds)) / SAMPLERATE
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


def peak_frequency(signal: np.ndarray) -> float:
    spectrum = np.abs(np.fft.rfft(signal))
    freqs = np.fft.rfftfreq(len(signal), 1 / SAMPLERATE)
    return float(freqs[spectrum.argmax()])


def test_pitch_shifts_up_by_the_factor():
    shifter = PitchShifter(1.10, SAMPLERATE)
    out = run_through(shifter, sine(440.0))
    measured = peak_frequency(out[SAMPLERATE:])  # skip warm-up second
    assert abs(measured - 440.0 * 1.10) < 5.0


def test_pitch_shifts_down_by_the_factor():
    shifter = PitchShifter(0.95, SAMPLERATE)
    out = run_through(shifter, sine(440.0))
    measured = peak_frequency(out[SAMPLERATE:])
    assert abs(measured - 440.0 * 0.95) < 5.0


def test_output_length_always_equals_input_length():
    # The live-audio invariant: any drift here would desync the stream.
    shifter = PitchShifter(1.07, SAMPLERATE)
    for size in (256, 1024, 4096):
        assert len(shifter.process(np.zeros(size, np.float32))) == size


def test_output_is_finite_and_bounded():
    # Crossfade gains must sum to ~1: no NaNs, no loudness explosion.
    shifter = PitchShifter(1.05, SAMPLERATE)
    out = run_through(shifter, sine(300.0))
    assert np.isfinite(out).all()
    assert np.abs(out).max() < 1.5
