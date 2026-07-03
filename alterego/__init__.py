"""alterego — a terminal-first content studio for camera-shy builders.

The pipeline has four independent stages, each its own module:

    record   (recorder.py)  -> capture webcam + screen + mic with ffmpeg
    disguise (disguise.py)  -> warp facial geometry so you look different
    enhance  (enhance.py)   -> fix lighting, white balance, and color
    cut      (cuts.py)      -> remove silent gaps to tighten pacing

Every stage reads a video file and writes a new one, so you can run them
in any order, re-run one stage without redoing the others, and inspect
the output between steps. That "files as the interface" design is what
makes the tool debuggable — and it's why it works on a 4 GB machine:
we never hold a whole video in memory, only one frame at a time.
"""

__version__ = "0.1.0"
