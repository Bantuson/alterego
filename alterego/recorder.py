"""Record webcam, microphone, and screen straight from the terminal.

On Windows, ffmpeg exposes cameras and mics through DirectShow
("dshow") and the screen through "gdigrab". We spawn ffmpeg as a
subprocess and let it do the heavy lifting — encoding happens in C,
not Python, which is what makes recording viable on 4 GB of RAM.

Encoding choices, and why:
  - libx264 -preset ultrafast : cheapest CPU cost while recording.
    The file is bigger than it could be, but we re-encode in post
    anyway, so we optimize for "don't drop frames", not file size.
  - -crf 23                   : sane visual quality for talking heads.
  - -pix_fmt yuv420p          : the pixel format every player supports.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .ffmpeg_tools import find_ffmpeg, probe_stderr

RECORDINGS_DIR = Path("recordings")

ENCODE_ARGS = [
    "-c:v", "libx264",
    "-preset", "ultrafast",
    "-crf", "23",
    "-pix_fmt", "yuv420p",
]


def list_devices() -> str:
    """Return ffmpeg's list of cameras and microphones on this machine.

    Run this first — you need the exact device names (in quotes) to
    record. The command "fails" by design (there is no output file),
    which is why we read stderr instead of checking the exit code.
    """
    return probe_stderr(["-list_devices", "true", "-f", "dshow", "-i", "dummy"])


def list_camera_modes(camera: str) -> str:
    """Return the resolutions and frame rates a camera actually supports.

    dshow rejects any mode the hardware doesn't offer (a cheap webcam
    often maxes out at 640x480), so we never *force* a mode by default —
    but if you want to pick one explicitly, this shows the menu.
    """
    return probe_stderr(["-f", "dshow", "-list_options", "true", "-i", f"video={camera}"])


def _start_ffmpeg(args: list[str]) -> subprocess.Popen:
    """Start ffmpeg with stdin open so we can stop it gracefully.

    Sending the letter "q" to ffmpeg's stdin is the clean way to stop:
    it finishes writing the file header so the video stays playable.
    Killing the process instead can corrupt the recording.
    """
    return subprocess.Popen(
        [find_ffmpeg(), "-hide_banner", "-loglevel", "warning"] + args,
        stdin=subprocess.PIPE,
    )


def _stop_ffmpeg(proc: subprocess.Popen) -> None:
    try:
        proc.stdin.write(b"q")
        proc.stdin.flush()
        proc.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        proc.terminate()


def record(
    camera: str | None,
    mic: str | None,
    screen: bool,
    out_stem: str = "take",
    fps: int | None = None,
    size: str | None = None,
) -> list[Path]:
    """Record camera and/or screen until the user presses Enter.

    Camera and screen are captured by two SEPARATE ffmpeg processes
    writing two separate files. That is deliberate: compositing them
    live would double the CPU load and risk dropped frames on a small
    machine. Combining the two videos is an editing decision anyway —
    better made in post, when you can retry for free.

    `fps`/`size` default to None = let the camera use its native mode.
    dshow hard-rejects any mode the hardware doesn't support, so
    forcing one is opt-in (check `alterego devices --modes` first).
    """
    RECORDINGS_DIR.mkdir(exist_ok=True)
    procs: list[subprocess.Popen] = []
    outputs: list[Path] = []

    if camera:
        cam_out = RECORDINGS_DIR / f"{out_stem}_camera.mp4"
        # dshow takes video and audio in one input string, ':' separated.
        input_spec = f"video={camera}" + (f":audio={mic}" if mic else "")
        args = ["-y", "-f", "dshow", "-rtbufsize", "100M"]
        # Big real-time buffer (above) so a slow disk doesn't drop frames.
        if fps:
            args += ["-framerate", str(fps)]
        if size:
            args += ["-video_size", size]
        args += [
            "-i", input_spec,
            *ENCODE_ARGS,
            "-c:a", "aac",
            str(cam_out),
        ]
        procs.append(_start_ffmpeg(args))
        outputs.append(cam_out)

    if screen:
        screen_out = RECORDINGS_DIR / f"{out_stem}_screen.mp4"
        args = [
            "-y",
            "-f", "gdigrab",
            # 15 fps is plenty for screen content and halves the CPU cost.
            "-framerate", "15",
            "-i", "desktop",
            *ENCODE_ARGS,
            str(screen_out),
        ]
        procs.append(_start_ffmpeg(args))
        outputs.append(screen_out)

    if not procs:
        raise ValueError("Nothing to record: pass a camera name and/or --screen.")

    # A capture process that is going to fail (device busy, unsupported
    # mode, typo'd name) dies within a second or two. Catch that NOW —
    # nothing hurts like finding out after a 20-minute take.
    time.sleep(2.0)
    dead = [(p, out) for p, out in zip(procs, outputs) if p.poll() is not None]
    if dead:
        for _, out in dead:
            print(f"✗ {out.name} failed to start.")
        print(
            "  Common causes: camera already in use (close the preview!), "
            "or a mode it doesn't support — see `alterego devices --modes`."
        )
        for proc, out in zip(procs, outputs):
            if proc.poll() is None:
                _stop_ffmpeg(proc)  # don't leave the survivor recording
        raise SystemExit(1)

    print(f"● Recording {len(procs)} stream(s)... press Enter to stop.")
    input()

    for proc in procs:
        _stop_ffmpeg(proc)

    for path in outputs:
        print(f"  saved {path}")
    return outputs
