"""Cut silent gaps so the video keeps pace — the #1 edit for talking heads.

Strategy: ask ffmpeg's `silencedetect` filter WHERE the silences are
(it prints timestamps), invert that list into "keep" segments, then
have ffmpeg trim and concatenate those segments. All the audio science
lives in ffmpeg; our job is interval arithmetic — parsing, inverting,
and padding time ranges. That kind of glue logic is 80% of real-world
media programming.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .ffmpeg_tools import get_duration, probe_stderr, run_ffmpeg

Segment = tuple[float, float]  # (start_seconds, end_seconds)


def detect_silences(
    video: str | Path,
    noise_db: float = -35.0,
    min_silence: float = 0.6,
) -> list[Segment]:
    """Return (start, end) times of every silence in the video.

    `noise_db` is the "anything quieter than this counts as silence"
    threshold. -35 dB works for a voice close to the mic; if your room
    is noisy, raise it toward -25 so the hum doesn't count as speech.
    `min_silence` ignores tiny pauses — natural speech rhythm we keep.
    """
    stderr = probe_stderr([
        "-i", str(video),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f", "null", "-",
    ])
    # ffmpeg prints lines like:
    #   [silencedetect @ ...] silence_start: 12.34
    #   [silencedetect @ ...] silence_end: 15.60 | silence_duration: 3.26
    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", stderr)]
    # A video can end mid-silence: one more start than ends.
    if len(starts) == len(ends) + 1:
        ends.append(get_duration(video))
    return list(zip(starts, ends))


def keep_segments(
    silences: list[Segment],
    duration: float,
    padding: float = 0.15,
) -> list[Segment]:
    """Invert silence ranges into the speech ranges we keep.

    `padding` leaves a beat of quiet on each side of every cut —
    without it, sentences slam into each other and the edit sounds
    robotic. Pacing is padding.
    """
    kept: list[Segment] = []
    cursor = 0.0
    for silence_start, silence_end in silences:
        keep_end = min(silence_start + padding, duration)
        if keep_end - cursor > 0.05:  # skip slivers too short to keep
            kept.append((cursor, keep_end))
        cursor = max(silence_end - padding, cursor)
    if duration - cursor > 0.05:
        kept.append((cursor, duration))
    return kept


def cut_video(video: str | Path, out: str | Path, segments: list[Segment]) -> None:
    """Trim to the given segments and join them into one video.

    We build an ffmpeg filter graph: one trim per segment for video
    (`trim`) and audio (`atrim`), then `concat` glues them in order.
    `setpts`/`asetpts` restart each segment's clock at zero — without
    that, players see gaps in the timestamps and stutter.

    The graph is written to a temp file (-filter_complex_script)
    because with many segments the text overflows the Windows
    command-line length limit.
    """
    if not segments:
        raise ValueError("No segments to keep — the whole video was silent?")

    parts = []
    for i, (start, end) in enumerate(segments):
        parts.append(
            f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}];"
            f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}];"
        )
    chain = "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
    parts.append(f"{chain}concat=n={len(segments)}:v=1:a=1[v][a]")
    script = "\n".join(parts)

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        run_ffmpeg([
            "-y",
            "-i", str(video),
            "-filter_complex_script", script_path,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "21",
            "-c:a", "aac",
            str(out),
        ])
    finally:
        Path(script_path).unlink(missing_ok=True)


def process_video(
    src: str | Path,
    dst: str | Path,
    noise_db: float = -35.0,
    min_silence: float = 0.6,
) -> None:
    """Detect silences, report the savings, and write the tightened cut."""
    duration = get_duration(src)
    silences = detect_silences(src, noise_db, min_silence)
    segments = keep_segments(silences, duration)

    kept = sum(end - start for start, end in segments)
    print(
        f"  {len(silences)} silences found — keeping {kept:.1f}s "
        f"of {duration:.1f}s ({kept / duration:.0%})"
    )
    cut_video(src, dst, segments)
    print(f"  saved {dst}")
