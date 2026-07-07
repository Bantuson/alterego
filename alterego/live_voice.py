"""Real-time voice shifting: your alter ego's voice, live.

Post-processing (voice.py) hands the whole audio file to ffmpeg. Live
audio arrives in ~23 ms blocks from the microphone, and each block
must leave for the speakers/virtual-cable before the next one lands —
there is no "whole file" to hand over. So live mode needs a shifter
that works one small block at a time.

The algorithm here is the classic two-tap delay-line pitch shifter —
the same trick inside guitar "Whammy" pedals since the 1980s:

  * Incoming audio is written into a ring buffer (a short delay line).
  * A read head plays audio back from that buffer at a slightly
    different SPEED than it was written (faster = higher pitch).
  * A head moving faster than the writer must eventually catch up —
    so when it runs out of buffer, it jumps back. The jump would
    click, so we run TWO read heads half a buffer apart and crossfade
    to whichever one is far from its jump point. The click hides
    inside the silence of the crossfade.

Quality: a faint chorus-like shimmer, perfectly fine for the ±3–7%
shifts our identity uses. Latency: about half the window (~25 ms).
"""

from __future__ import annotations

import numpy as np


class PitchShifter:
    """Block-by-block pitch shifter with constant input/output rate."""

    def __init__(self, factor: float, samplerate: int, window_ms: float = 50.0) -> None:
        self.factor = factor
        # The delay window the read heads roam inside. Longer = fewer
        # jumps (less shimmer) but more latency.
        self.window = int(samplerate * window_ms / 1000)
        # Ring buffer holds a few windows of history. Sized generously
        # so block boundaries never outrun it.
        self.size = self.window * 4
        self.buffer = np.zeros(self.size, dtype=np.float32)
        self.write_pos = 0
        # How far behind the write head we are currently reading.
        # Advances by (1 - factor) per sample: factor > 1 means the
        # read head gains on the writer (delay shrinks) -> higher pitch.
        self.phase = 0.0

    def _read_at(self, delays: np.ndarray, write_positions: np.ndarray) -> np.ndarray:
        """Read the buffer at fractional delays (linear interpolation).

        A delay of 10.4 samples means "40% of the way between the
        sample 10 back and the sample 11 back" — fractional reads are
        what make the pitch change smooth instead of steppy.
        """
        positions = (write_positions - delays) % self.size
        lower = np.floor(positions).astype(int)
        frac = (positions - lower).astype(np.float32)
        upper = (lower + 1) % self.size
        return self.buffer[lower] * (1 - frac) + self.buffer[upper] * frac

    def process(self, block: np.ndarray) -> np.ndarray:
        """Shift one block. Input and output have identical length —
        that invariant is what keeps live audio flowing without drift."""
        n = len(block)
        # 1. Write the new audio into the ring buffer.
        idx = (self.write_pos + np.arange(n)) % self.size
        self.buffer[idx] = block
        write_positions = self.write_pos + np.arange(n) + 1

        # 2. Each output sample reads from a delay that drifts by
        #    (1 - factor) per sample, wrapped into [0, window).
        drift = 1.0 - self.factor
        delays1 = (self.phase + np.arange(n) * drift) % self.window
        # The second head sits half a window away — maximally far from
        # the first head's jump point.
        delays2 = (delays1 + self.window / 2) % self.window

        # 3. Triangular crossfade: a head's gain hits zero exactly
        #    where that head jumps, so the jump is inaudible.
        x = delays1 / self.window  # 0..1 position within the window
        gain1 = 1.0 - np.abs(2.0 * x - 1.0)
        gain2 = 1.0 - gain1

        out = gain1 * self._read_at(delays1, write_positions) + gain2 * self._read_at(
            delays2, write_positions
        )

        # 4. Advance state for the next block.
        self.write_pos = (self.write_pos + n) % self.size
        self.phase = (self.phase + n * drift) % self.window
        return out.astype(np.float32)


def run_voice_loop(
    factor: float,
    input_device: str | int | None = None,
    output_device: str | int | None = None,
    samplerate: int = 44100,
    blocksize: int = 1024,
) -> None:
    """Microphone -> pitch shift -> output device, until interrupted.

    Point `output_device` at a virtual cable (e.g. VB-Audio "CABLE
    Input") and select the cable's other end as the mic in OBS/Zoom —
    that makes this the system-wide alter-ego microphone. Left at the
    default speakers it is only a monitor (and will feed back if the
    mic can hear them).
    """
    import sounddevice as sd

    shifter = PitchShifter(factor, samplerate)

    def callback(indata, outdata, _frames, _time, status):
        if status:
            print(f"  audio: {status}")
        # FAIL CLOSED: if anything goes wrong in the shifter, output
        # silence — never the raw microphone. Leaking your real voice
        # live is worse than a moment of dead air.
        try:
            outdata[:, 0] = shifter.process(indata[:, 0])
        except Exception:
            outdata.fill(0)

    with sd.Stream(
        samplerate=samplerate,
        blocksize=blocksize,
        channels=1,
        dtype="float32",
        device=(input_device, output_device),
        callback=callback,
    ):
        print(f"● voice live (pitch x{factor}) — Ctrl+C to stop")
        import time

        while True:
            time.sleep(0.5)


def list_audio_devices() -> str:
    import sounddevice as sd

    return str(sd.query_devices())
