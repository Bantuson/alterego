"""The studio: a local web control room for alterego.

Architecture, and why it's shaped this way:

  * The browser is the RENDERER (Three.js constellation, panels); this
    server is the HANDS. Every privileged thing — reading the webcam,
    saving identities, running pipelines — happens here, in the same
    Python that owns those features.
  * Pipelines run as SUBPROCESSES of the CLI, not as imported calls.
    The CLI is already the tested interface; the UI drives exactly
    what a terminal user drives, so the two can never disagree. Their
    stdout streams to the browser as Server-Sent Events — the studio
    console shows the same honest lines the terminal would.
  * stdlib http.server only. A local single-user tool does not need a
    web framework; what it needs is a small surface you can read.

Security posture: binds 127.0.0.1 (never reachable from the network),
serves only files inside ui/, and jobs are built from a WHITELIST of
verbs + validated fields — the browser can never compose a raw
command line. Face scans cache to .alterego-cache/ (gitignored;
that file is literal biometric geometry and never leaves the machine).
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

UI_DIR = Path(__file__).resolve().parent / "ui"
CACHE_DIR = Path(".alterego-cache")
SCAN_CACHE = CACHE_DIR / "scan.json"

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/three.module.min.js": ("three.module.min.js", "text/javascript; charset=utf-8"),
}


class Job:
    """One running pipeline: a subprocess plus its captured lines."""

    def __init__(self, args: list[str]) -> None:
        self.lines: deque[str] = deque(maxlen=500)
        self.done = False
        self.ok: bool | None = None
        self.proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        for line in self.proc.stdout:
            # Progress lines use \r to redraw in a terminal; the web
            # console wants discrete lines instead.
            self.lines.append(line.rstrip("\r\n").split("\r")[-1])
        self.proc.wait()
        self.ok = self.proc.returncode == 0
        self.lines.append("✓ done" if self.ok else f"✗ exited {self.proc.returncode}")
        self.done = True


JOBS: dict[str, Job] = {}
LIVE_PROC: dict[str, subprocess.Popen | None] = {"proc": None}


def _cli(*args: str) -> list[str]:
    """A pipeline command, run by the same interpreter (the venv)."""
    return [sys.executable, "-m", "alterego.cli", *args]


def build_job_args(payload: dict) -> list[str]:
    """Translate a UI request into a CLI invocation — whitelist only.

    The browser sends {verb, video, identities, image, flags...}; we
    assemble argv ourselves. Unknown verbs or fields are ignored or
    rejected, so the UI cannot run anything a terminal user couldn't.
    """
    verb = payload.get("verb")
    video = str(payload.get("video", ""))
    if not video or not Path(video).exists():
        raise ValueError(f"video not found: {video}")

    if verb == "ship":
        args = _cli("ship", video)
        if payload.get("identity"):
            args += ["--identity", str(payload["identity"])]
        if payload.get("image"):
            args += ["--image", str(payload["image"])]
        for flag in ("night", "no_fillers", "no_voice", "no_background"):
            if payload.get(flag):
                args.append("--" + flag.replace("_", "-"))
        return args

    if verb == "disguise":
        args = _cli("disguise", video)
        for name in payload.get("identities", []) or []:
            args += ["--identity", str(name)]
        return args

    if verb == "prep":
        return _cli("prep", video)

    if verb == "clip":
        title = str(payload.get("title", "")).strip()
        if not title:
            raise ValueError("clip needs a title")
        return _cli("clip", video, "--title", title)

    raise ValueError(f"unknown verb: {verb}")


def scan_face() -> list[list[float]]:
    """Average a webcam burst into one 3D landmark set (478 x [x,y,z]).

    Cached so reopening the studio doesn't demand a re-scan. The cache
    is the user's real facial geometry: gitignored, local-only.
    """
    import cv2
    import numpy as np

    from .faces import FaceLandmarker

    capture = cv2.VideoCapture(0)
    if not capture.isOpened():
        raise RuntimeError("no webcam found")
    landmarker = FaceLandmarker()
    collected: list = []
    attempts = 0
    try:
        while len(collected) < 12 and attempts < 120:
            ok, frame = capture.read()
            attempts += 1
            if not ok:
                break
            landmarks = landmarker.detect_3d(frame)
            if landmarks is not None:
                collected.append(landmarks)
    finally:
        capture.release()
        landmarker.close()
    if len(collected) < 6:
        raise RuntimeError("could not see a face — add light, look at the camera")

    points = np.mean(collected, axis=0)
    CACHE_DIR.mkdir(exist_ok=True)
    data = [[round(float(v), 2) for v in p] for p in points]
    SCAN_CACHE.write_text(json.dumps(data))
    return data


class StudioHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass  # keep the terminal quiet; the browser console is the UI

    # -- helpers ------------------------------------------------------
    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    # -- GET ----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        # Route on the path alone — "/?demo" must still serve "/".
        self.path = self.path.split("?")[0]
        if self.path in STATIC:
            name, mime = STATIC[self.path]
            content = (UI_DIR / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if self.path == "/api/identities":
            from .settings import SETTINGS_FILE, list_identities, load_identity

            out = []
            if SETTINGS_FILE.exists():
                identity = load_identity()
                out.append({"name": None, "knobs": identity.profile.to_dict()})
            for name in list_identities():
                identity = load_identity(name)
                out.append({"name": name, "knobs": identity.profile.to_dict()})
            self._json(out)
            return

        if self.path == "/api/scan/cached":
            if SCAN_CACHE.exists():
                self._json({"points": json.loads(SCAN_CACHE.read_text())})
            else:
                self._json({"points": None})
            return

        if self.path == "/api/files":
            videos = []
            for folder in (Path("recordings"), Path(".")):
                if folder.exists():
                    videos += [
                        str(p) for p in folder.glob("*.mp4")
                    ] + [str(p) for p in folder.glob("*.mov")]
            self._json(sorted(set(videos)))
            return

        if self.path.startswith("/api/jobs/"):
            job = JOBS.get(self.path.split("/")[3])
            if job is None:
                self._json({"error": "no such job"}, 404)
                return
            # Server-Sent Events: stream console lines as they appear.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            sent = 0
            try:
                while True:
                    lines = list(job.lines)
                    for line in lines[sent:]:
                        self.wfile.write(f"data: {json.dumps(line)}\n\n".encode())
                    sent = len(lines)
                    self.wfile.flush()
                    if job.done and sent == len(job.lines):
                        self.wfile.write(b"event: end\ndata: {}\n\n")
                        return
                    time.sleep(0.25)
            except (ConnectionAbortedError, BrokenPipeError):
                return

        if self.path == "/api/live/status":
            proc = LIVE_PROC["proc"]
            running = proc is not None and proc.poll() is None
            self._json({"running": running})
            return

        self._json({"error": "not found"}, 404)

    # -- POST ---------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path == "/api/scan":
                self._json({"points": scan_face()})
                return

            if self.path == "/api/identities":
                import numpy as np

                from .disguise import DisguiseProfile
                from .settings import load_identity, save_identity

                data = self._body()
                profile = DisguiseProfile.from_dict(data["knobs"])
                name = data.get("name") or None
                existing = load_identity(name)
                voice_seed = (
                    existing.voice_seed
                    if existing
                    else int(np.random.default_rng().integers(0, 100_000))
                )
                path = save_identity(profile, 1.0, voice_seed, name=name)
                self._json({"saved": str(path)})
                return

            if self.path == "/api/jobs":
                args = build_job_args(self._body())
                job_id = uuid4().hex[:8]
                JOBS[job_id] = Job(args)
                self._json({"id": job_id})
                return

            if self.path == "/api/live/start":
                if LIVE_PROC["proc"] is not None and LIVE_PROC["proc"].poll() is None:
                    raise ValueError("live already running")
                data = self._body()
                args = _cli("live", "--window")  # window mode: visible, stoppable
                if data.get("identity"):
                    args += ["--identity", str(data["identity"])]
                if data.get("image"):
                    args += ["--image", str(data["image"])]
                if data.get("virtual"):
                    args.remove("--window")
                LIVE_PROC["proc"] = subprocess.Popen(args)
                self._json({"running": True})
                return

            if self.path == "/api/live/stop":
                proc = LIVE_PROC["proc"]
                if proc is not None and proc.poll() is None:
                    proc.terminate()
                LIVE_PROC["proc"] = None
                self._json({"running": False})
                return

            self._json({"error": "not found"}, 404)
        except Exception as error:  # surface real reasons to the console
            self._json({"error": str(error)}, 400)


def run_studio(port: int = 4700, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), StudioHandler)
    url = f"http://127.0.0.1:{port}"
    print(f"● studio at {url}  (local only — Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstudio closed")
