"""Find and run ffmpeg — the one external program every stage leans on.

Why ffmpeg instead of pure Python? Reading/writing compressed video and
audio well is a decades-deep problem. The professional move is to let
ffmpeg handle encoding, audio, and container formats, and keep Python
for the interesting part: the per-frame computer vision.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


def find_ffmpeg() -> str:
    """Locate an ffmpeg executable, trying the most capable option first.

    Search order:
      1. PATH — a system install (winget/choco) has every feature,
         including the Windows device-capture inputs we need to record.
      2. The winget links folder — a fresh winget install updates PATH
         only for *new* terminals, so we check its known location too.
      3. The ffmpeg bundled with the imageio-ffmpeg package — always
         available after `uv sync`, fine for processing files, but its
         build may lack webcam/screen capture support.
    """
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path

    local_app = os.environ.get("LOCALAPPDATA", "")
    winget_link = Path(local_app) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
    if winget_link.exists():
        return str(winget_link)

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise RuntimeError(
            "ffmpeg not found. Install it with `winget install Gyan.FFmpeg` "
            "or run `uv sync` to get the bundled fallback."
        )


def run_ffmpeg(args: list[str], quiet: bool = True) -> subprocess.CompletedProcess:
    """Run ffmpeg with the given arguments and raise if it fails.

    `-hide_banner` and `-loglevel error` keep the terminal readable;
    ffmpeg is famously chatty otherwise.
    """
    cmd = [find_ffmpeg(), "-hide_banner"]
    if quiet:
        cmd += ["-loglevel", "error"]
    cmd += args
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def probe_stderr(args: list[str]) -> str:
    """Run ffmpeg and return its stderr text WITHOUT raising on failure.

    ffmpeg prints analysis output (device lists, silence timestamps,
    durations) to stderr, and some of those commands "fail" by design —
    e.g. listing devices exits non-zero because no output file is given.
    """
    cmd = [find_ffmpeg(), "-hide_banner"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stderr


def get_duration(video: str | Path) -> float:
    """Read a video's duration in seconds from ffmpeg's analysis output."""
    stderr = probe_stderr(["-i", str(video)])
    # ffmpeg prints a line like:  Duration: 00:01:23.45, start: ...
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", stderr)
    if not match:
        raise ValueError(f"Could not read duration of {video}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def prep_for_pipeline(src: str | Path, out: str | Path, max_height: int = 720) -> None:
    """Normalize any outside footage (usually phone video) for the pipeline.

    Phone cameras produce two things OpenCV chokes on:
      * HEVC/H.265 encoding — great compression, poor decoder support;
      * variable frame rate — frames arrive when the sensor feels like
        it, which breaks any tool that assumes a steady clock.

    This transcodes to the boring, universally-readable combination
    (H.264, constant 30 fps) and caps height at `max_height` so a
    4K phone clip doesn't take an hour to disguise on a small CPU.
    720p is plenty for social media.
    """
    run_ffmpeg(
        [
            "-y",
            "-i", str(src),
            # fps first (fixes variable frame rate), then scale.
            # -2 = "pick a width that keeps aspect and stays even"
            # (H.264 requires even dimensions).
            "-vf", f"fps=30,scale=-2:'min({max_height},ih)'",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-c:a", "aac",
            str(out),
        ]
    )


def remux_audio(processed_video: str | Path, original_video: str | Path, out: str | Path) -> None:
    """Copy the audio track from the original file onto a processed one.

    OpenCV's video writer is video-only, so after we warp or color-grade
    frames the sound is gone. This puts it back without re-encoding
    (`-c copy` = instant, lossless). The `?` in `-map 1:a?` means
    "take audio if it exists" — screen recordings may have none.
    """
    run_ffmpeg(
        [
            "-y",
            "-i", str(processed_video),
            "-i", str(original_video),
            "-map", "0:v",
            "-map", "1:a?",
            "-c", "copy",
            "-shortest",
            str(out),
        ]
    )
