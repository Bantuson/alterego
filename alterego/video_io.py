"""Stream a video through a per-frame function, one frame at a time.

This is the memory trick that makes the whole project work on 4 GB:
a single 720p frame is ~2.6 MB as a numpy array, but a 5-minute video
is ~24,000 frames. Load-everything-then-process would need gigabytes;
read-one, process-one, write-one needs almost nothing.

Both `disguise` and `enhance` reuse this loop — they only differ in
the function applied to each frame.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .ffmpeg_tools import remux_audio

# A frame function takes a BGR image (OpenCV's channel order) and
# returns a new one of the same size.
FrameFn = Callable[[np.ndarray], np.ndarray]


def stream_video(src: str | Path, dst: str | Path, frame_fn: FrameFn) -> None:
    """Apply `frame_fn` to every frame of `src` and write `dst`.

    OpenCV's writer drops the audio track, so we write video to a temp
    file first, then remux the original audio back in with ffmpeg.
    """
    src, dst = Path(src), Path(dst)
    capture = cv2.VideoCapture(str(src))
    if not capture.isOpened():
        raise FileNotFoundError(f"Could not open video: {src}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

    temp = dst.with_name(dst.stem + "_noaudio.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(temp), fourcc, fps, (width, height))

    started = time.time()
    done = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:  # end of video
                break
            writer.write(frame_fn(frame))
            done += 1
            if done % 100 == 0:
                rate = done / (time.time() - started)
                print(f"  {done}/{total} frames ({rate:.0f} fps)", end="\r")
    finally:
        capture.release()
        writer.release()

    print(f"  {done}/{total} frames — remuxing audio...")
    remux_audio(temp, src, dst)
    temp.unlink()
    print(f"  saved {dst}")
