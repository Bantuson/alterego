"""Turn a polished take into a branded 9:16 social clip via Remotion.

Division of labor:
  * Python (this file): transcribe for captions, measure the video,
    stage assets into remotion/public/, write a props JSON — all the
    DATA decisions.
  * Remotion (remotion/src/): fonts, layout, animation, rendering —
    all the DESIGN decisions, in React, where design tooling lives.

The two meet at a JSON file. That contract means you can restyle the
clip in remotion/src/Clip.tsx without touching Python, and improve
transcription without touching React.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .ffmpeg_tools import get_duration

REMOTION_DIR = Path(__file__).resolve().parent.parent / "remotion"

# The brand, as data. Tweak here (or per-clip via CLI flags).
DEFAULT_ACCENT = "#39E508"
DEFAULT_HANDLE = "@alterego"


def words_to_captions(words: list[tuple[str, float, float]]) -> list[dict]:
    """Convert whisper words to Remotion's Caption JSON format.

    Whisper gives seconds; Remotion wants milliseconds. Whisper's raw
    tokens carry their own leading space (" Hello") — we keep them
    verbatim because caption layout is whitespace-sensitive.
    """
    return [
        {
            "text": text,
            "startMs": round(start * 1000),
            "endMs": round(end * 1000),
            "timestampMs": round((start + end) / 2 * 1000),
            "confidence": None,
        }
        for text, start, end in words
    ]


def build_props(video: str | Path, title: str, handle: str, accent: str) -> dict:
    """Transcribe + measure the video, stage assets, return render props."""
    from .fillers import transcribe_words

    video = Path(video)
    public = REMOTION_DIR / "public"
    public.mkdir(exist_ok=True)

    print("  transcribing for captions...")
    captions = words_to_captions(transcribe_words(video))
    (public / "captions.json").write_text(json.dumps(captions))

    # Remotion can only load assets from its public/ folder.
    shutil.copy(video, public / "clip.mp4")

    return {
        "videoFile": "clip.mp4",
        "captionsFile": "captions.json",
        "title": title,
        "handle": handle,
        "accent": accent,
        "durationInSeconds": get_duration(video),
    }


def render(
    video: str | Path,
    out: str | Path,
    title: str,
    handle: str = DEFAULT_HANDLE,
    accent: str = DEFAULT_ACCENT,
) -> None:
    """Render the branded clip. Needs `npm install` done in remotion/."""
    npx = shutil.which("npx")
    if npx is None:
        raise SystemExit("npx not found — install Node.js to render clips.")
    if not (REMOTION_DIR / "node_modules").exists():
        raise SystemExit(
            f"Remotion dependencies missing. Run: cd {REMOTION_DIR} && npm install"
        )

    props = build_props(video, title, handle, accent)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(props, f)
        props_path = f.name

    print("  rendering with Remotion (this is the slow part)...")
    try:
        subprocess.run(
            [
                npx,
                "remotion", "render", "Clip",
                str(Path(out).resolve()),
                f"--props={props_path}",
                # One browser tab: kind to a 4 GB machine. Renders take
                # longer but never exhaust memory.
                "--concurrency=1",
            ],
            cwd=REMOTION_DIR,
            check=True,
        )
    finally:
        Path(props_path).unlink(missing_ok=True)
    print(f"  saved {out}")
