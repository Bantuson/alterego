"""The terminal interface. One subcommand per pipeline stage.

Typical session:

    uv run alterego devices                      # find your camera/mic names
    uv run alterego record --camera "HD Webcam" --mic "Microphone" --screen
    uv run alterego preview --seed 1337          # audition your alter ego live
    uv run alterego disguise take_camera.mp4 --seed 1337
    uv run alterego enhance take_camera_alterego.mp4
    uv run alterego cut take_camera_alterego_graded.mp4

Built on argparse (standard library): every Python installation has
it, and the subcommand pattern here is the same one used by git, uv,
and docker.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _default_out(src: str, suffix: str) -> str:
    """take.mp4 + 'alterego' -> take_alterego.mp4 (keeps stages traceable)."""
    path = Path(src)
    return str(path.with_name(f"{path.stem}_{suffix}{path.suffix}"))


def cmd_devices(args: argparse.Namespace) -> None:
    from .recorder import list_camera_modes, list_devices

    if args.modes:
        print(list_camera_modes(args.modes))
        return
    print(list_devices())
    print('Use the names in quotes above, e.g. --camera "HD WebCam".')


def cmd_record(args: argparse.Namespace) -> None:
    from .recorder import record

    record(
        camera=args.camera,
        mic=args.mic,
        screen=args.screen,
        out_stem=args.name,
        fps=args.fps,
        size=args.size,
    )


def cmd_preview(args: argparse.Namespace) -> None:
    """Live webcam preview of the disguise — press N for a new random
    seed, K to KEEP the current one (saves to alterego.json), Q to
    quit. Use this to *choose* your alter ego before you ever record."""
    import cv2
    import numpy as np

    from .disguise import DisguiseProfile, apply_disguise
    from .faces import FaceLandmarker, LandmarkSmoother
    from .settings import save_identity

    capture = cv2.VideoCapture(args.camera_index)
    if not capture.isOpened():
        raise SystemExit(f"No webcam at index {args.camera_index}.")

    seed = args.seed
    profile = DisguiseProfile.from_seed(seed, args.strength)
    landmarker = FaceLandmarker()
    smoother = LandmarkSmoother()
    print(f"seed={seed} | N = new seed, K = keep this face, Q = quit")

    while True:
        ok, frame = capture.read()
        if not ok:
            break
        # Half resolution keeps the preview responsive on a small CPU;
        # the full-quality pass happens later, offline, in `disguise`.
        frame = cv2.resize(frame, None, fx=0.5, fy=0.5)
        landmarks = smoother.update(landmarker.detect(frame))
        if landmarks is not None:
            frame = apply_disguise(frame, landmarks, profile)
        cv2.imshow("alterego preview", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("n"):
            seed = int(np.random.default_rng().integers(0, 100_000))
            profile = DisguiseProfile.from_seed(seed, args.strength)
            print(f"seed={seed}")
        if key == ord("k"):
            # The knobs are the identity; the seed doubles as the
            # voice seed so face and voice stay a matched pair.
            path = save_identity(profile, args.strength, voice_seed=seed)
            print(f"✓ kept seed={seed} -> {path} (disguise now uses it by default)")

    capture.release()
    cv2.destroyAllWindows()
    landmarker.close()


KNOB_FLAGS = {
    "jaw": "jaw_width",
    "chin": "chin_length",
    "eyes_apart": "eye_spacing",
    "nose_length": "nose_length",
    "nose_width": "nose_width",
    "mouth": "mouth_width",
    "lips": "lip_fullness",
    "brows": "brow_height",
}


def cmd_design(args: argparse.Namespace) -> None:
    """Craft the alter ego deliberately: explicit knobs or a reference face."""
    import numpy as np

    from .disguise import DisguiseProfile
    from .settings import load_identity, save_identity

    existing = load_identity()

    # Named personas load/save from identities/<name>.json; the
    # default (no --name) remains alterego.json.
    existing = load_identity(args.name) or existing

    if args.like:
        from .design import (
            knobs_from_reference,
            landmarks_from_camera,
            landmarks_from_image,
            measure_ratios,
        )

        print("  measuring your face (look at the camera, neutral expression)...")
        mine = measure_ratios(landmarks_from_camera(args.camera_index))
        target = measure_ratios(landmarks_from_image(args.like))
        profile = knobs_from_reference(mine, target)
        print("  knobs derived from reference (clamped to the naturalness budget):")
    else:
        # Start from the saved face (tweak) or a blank one (fresh),
        # then apply whichever knobs were passed.
        base = existing.profile.to_dict() if (existing and args.tweak) else {
            name: 0.0 for name in KNOB_FLAGS.values()
        }
        for flag, knob in KNOB_FLAGS.items():
            value = getattr(args, flag)
            if value is not None:
                base[knob] = float(np.clip(value, -1.0, 1.0))
        profile = DisguiseProfile.from_dict(base)

    for knob, value in profile.to_dict().items():
        print(f"    {knob:12s} {value:+.2f}")

    # Voice stays whatever it was: redesigning your face must never
    # silently change how you sound. Fresh identities roll one.
    voice_seed = existing.voice_seed if existing else int(
        np.random.default_rng().integers(0, 100_000)
    )

    if not args.save:
        # Audition before committing — the preview is the final judge.
        import cv2

        from .disguise import apply_disguise
        from .faces import FaceLandmarker, LandmarkSmoother

        capture = cv2.VideoCapture(args.camera_index)
        if not capture.isOpened():
            raise SystemExit(f"No webcam at index {args.camera_index}.")
        landmarker = FaceLandmarker()
        smoother = LandmarkSmoother()
        print("previewing — K = keep this face, Q = quit without saving")
        kept = False
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame = cv2.resize(frame, None, fx=0.5, fy=0.5)
            landmarks = smoother.update(landmarker.detect(frame))
            if landmarks is not None:
                frame = apply_disguise(frame, landmarks, profile)
            cv2.imshow("alterego design", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("k"):
                kept = True
                break
        capture.release()
        cv2.destroyAllWindows()
        landmarker.close()
        if not kept:
            print("not saved.")
            return

    path = save_identity(profile, strength=1.0, voice_seed=voice_seed, name=args.name)
    print(f"✓ identity saved -> {path}")


def cmd_disguise(args: argparse.Namespace) -> None:
    from .disguise import DisguiseProfile, process_video
    from .settings import load_identity

    if args.seed is not None:
        profiles = [DisguiseProfile.from_seed(args.seed, args.strength)]
    else:
        names = args.identity or [None]
        profiles = []
        for name in names:
            identity = load_identity(name)
            if identity is None:
                raise SystemExit(
                    f"Identity {name or '(default)'} not found. Run "
                    "`alterego design --name <name>` or `alterego preview`."
                )
            profiles.append(identity.profile)
        label = ", ".join(n or "default" for n in names)
        print(f"using identit{'ies' if len(names) > 1 else 'y'}: {label}")

    out = args.out or _default_out(args.video, "alterego")
    process_video(args.video, out, profiles)


def cmd_prep(args: argparse.Namespace) -> None:
    from .ffmpeg_tools import prep_for_pipeline

    out = args.out or _default_out(args.video, "prep")
    prep_for_pipeline(args.video, out, max_height=args.max_height)
    print(f"  saved {out}")


def cmd_background(args: argparse.Namespace) -> None:
    from .background import process_video

    out = args.out or _default_out(args.video, "scene")
    process_video(
        args.video, out, image=args.image, blur=args.blur,
        harmonize_amount=args.harmonize,
    )


def cmd_enhance(args: argparse.Namespace) -> None:
    from .enhance import process_video

    out = args.out or _default_out(args.video, "graded")
    process_video(args.video, out, night=args.night)


def cmd_live(args: argparse.Namespace) -> None:
    from .settings import load_identity

    identity = load_identity(args.identity)
    if identity is None:
        raise SystemExit(
            "live needs your saved identity. Run `alterego preview` (K) or `alterego design`."
        )

    if args.list_audio:
        from .live_voice import list_audio_devices

        print(list_audio_devices())
        return

    if args.voice:
        # Voice runs on its own thread: audio blocks arrive on a hard
        # 23 ms clock that must never wait for a video frame.
        import threading

        from .live_voice import run_voice_loop
        from .voice import factor_from_seed

        threading.Thread(
            target=run_voice_loop,
            kwargs={
                "factor": factor_from_seed(identity.voice_seed),
                "input_device": args.audio_in,
                "output_device": args.audio_out,
            },
            daemon=True,
        ).start()

    from .live import run_live

    run_live(
        profile=identity.profile,
        backdrop=args.image,
        camera_index=args.camera_index,
        width=args.width,
        window=args.window,
        max_frames=args.frames,
    )


def cmd_clip(args: argparse.Namespace) -> None:
    from .clips import render

    out = args.out or _default_out(args.video, "clip")
    render(args.video, out, title=args.title, handle=args.handle, accent=args.accent)


def cmd_ship(args: argparse.Namespace) -> None:
    from .pipeline import ship

    ship(
        args.video,
        out=args.out,
        identity_name=args.identity,
        image=args.image,
        night=args.night,
        fillers=not args.no_fillers,
        voice=not args.no_voice,
        background=not args.no_background,
        keep=args.keep,
    )


def cmd_voice(args: argparse.Namespace) -> None:
    from .settings import load_identity
    from .voice import factor_from_seed, process_video

    factor = args.factor
    if factor is None:
        identity = load_identity(args.identity)
        if identity is None:
            raise SystemExit(
                "No --factor given and no saved identity to derive one from. "
                "Run `alterego preview` and press K, or pass --factor 1.05."
            )
        factor = factor_from_seed(identity.voice_seed)

    out = args.out or _default_out(args.video, "voiced")
    process_video(args.video, out, factor)


def cmd_cut(args: argparse.Namespace) -> None:
    from .cuts import process_video

    out = args.out or _default_out(args.video, "tight")
    process_video(
        args.video,
        out,
        noise_db=args.noise_db,
        min_silence=args.min_silence,
        cut_fillers=args.fillers,
        also_cut=tuple(args.also_cut),
    )


def main() -> None:
    # Windows terminals often use a legacy encoding (cp1252) that can't
    # print characters like ⚠ or ✓ — and Python then CRASHES on the
    # print. `errors="replace"` swaps unprintable characters for '?'
    # instead. A status symbol degrading beats a pipeline dying.
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        prog="alterego",
        description="Terminal content studio: record, disguise, enhance, cut.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("devices", help="list cameras and microphones")
    p.add_argument(
        "--modes",
        metavar="CAMERA",
        help="show supported resolutions/fps for this camera",
    )
    p.set_defaults(fn=cmd_devices)

    p = sub.add_parser("record", help="record webcam and/or screen until Enter")
    p.add_argument("--camera", help='camera name from `alterego devices`')
    p.add_argument("--mic", help='microphone name from `alterego devices`')
    p.add_argument("--screen", action="store_true", help="also record the screen")
    p.add_argument("--name", default="take", help="output filename stem")
    p.add_argument("--fps", type=int, help="force a frame rate (default: camera native)")
    p.add_argument("--size", help="force a resolution like 640x480 (default: camera native)")
    p.set_defaults(fn=cmd_record)

    p = sub.add_parser("preview", help="live disguise preview to pick a seed")
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--camera-index", type=int, default=0)
    p.set_defaults(fn=cmd_preview)

    p = sub.add_parser("design", help="craft your alter ego: knobs or a reference face")
    for flag, knob in KNOB_FLAGS.items():
        p.add_argument(
            f"--{flag.replace('_', '-')}", dest=flag, type=float, metavar="-1..1",
            help=f"set {knob}",
        )
    p.add_argument("--like", metavar="PHOTO", help="match a reference face's proportions")
    p.add_argument("--tweak", action="store_true", help="start from the saved identity")
    p.add_argument("--save", action="store_true", help="save without previewing")
    p.add_argument("--name", help="save as a named persona (identities/<name>.json)")
    p.add_argument("--camera-index", type=int, default=0)
    p.set_defaults(fn=cmd_design)

    p = sub.add_parser("disguise", help="apply alter ego(s) to a recording")
    p.add_argument("video")
    p.add_argument(
        "--identity", action="append", metavar="NAME",
        help="named persona; repeat for multi-person shots — first name "
        "= leftmost person (default: your main identity)",
    )
    p.add_argument("--seed", type=int, help="alter ego seed (overrides identities)")
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--out")
    p.set_defaults(fn=cmd_disguise)

    p = sub.add_parser("prep", help="normalize phone/outside footage for the pipeline")
    p.add_argument("video")
    p.add_argument("--max-height", type=int, default=720, help="downscale cap (default 720)")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_prep)

    p = sub.add_parser("background", help="replace or blur the background")
    p.add_argument("video")
    p.add_argument("--image", help="backdrop image OR video plate (omit to blur your real background)")
    p.add_argument("--blur", type=int, help="backdrop blur amount (default: 31 blur-mode, 9 image-mode)")
    p.add_argument(
        "--harmonize", type=float, default=0.4,
        help="color-match subject to backdrop, 0=off..1=full (default 0.4)",
    )
    p.add_argument("--out")
    p.set_defaults(fn=cmd_background)

    p = sub.add_parser("enhance", help="fix lighting, white balance, color")
    p.add_argument("video")
    p.add_argument("--night", action="store_true", help="salvage mode for underlit footage")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_enhance)

    p = sub.add_parser("live", help="real-time alter ego -> virtual camera (or preview)")
    p.add_argument("--identity", metavar="NAME", help="named persona to go live as")
    p.add_argument("--image", help="backdrop image or video plate")
    p.add_argument("--width", type=int, default=640, help="processing width (default 640)")
    p.add_argument("--camera-index", type=int, default=0)
    p.add_argument("--window", action="store_true", help="preview window instead of virtual camera")
    p.add_argument("--voice", action="store_true", help="also shift the microphone live")
    p.add_argument("--audio-in", help="input device name/index for --voice")
    p.add_argument("--audio-out", help='output device for --voice (e.g. "CABLE Input")')
    p.add_argument("--list-audio", action="store_true", help="list audio devices and exit")
    p.add_argument("--frames", type=int, help=argparse.SUPPRESS)  # for testing
    p.set_defaults(fn=cmd_live)

    p = sub.add_parser("clip", help="render a branded 9:16 social clip (Remotion)")
    p.add_argument("video", help="a polished take (ideally the output of ship)")
    p.add_argument("--title", required=True, help="the hook line shown at the top")
    p.add_argument("--handle", default="@alterego", help="your public handle")
    p.add_argument("--accent", default="#39E508", help="brand accent color")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_clip)

    p = sub.add_parser("ship", help="full pipeline: disguise, background, enhance, cut, voice")
    p.add_argument("video")
    p.add_argument("--identity", metavar="NAME", help="named persona to ship as")
    p.add_argument("--image", help="backdrop image or video plate for the background stage")
    p.add_argument("--night", action="store_true", help="salvage mode for underlit footage")
    p.add_argument("--no-fillers", action="store_true", help="skip filler-word removal")
    p.add_argument("--no-voice", action="store_true", help="skip the voice shift")
    p.add_argument("--no-background", action="store_true", help="skip background blur/replace")
    p.add_argument("--keep", action="store_true", help="keep intermediate stage files")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_ship)

    p = sub.add_parser("voice", help="pitch-shift your voice to your alter ego's")
    p.add_argument("video")
    p.add_argument("--identity", metavar="NAME", help="named persona for the voice")
    p.add_argument("--factor", type=float, help="pitch ratio (default: derived from saved seed)")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_voice)

    p = sub.add_parser("cut", help="remove silent gaps (and fillers with --fillers)")
    p.add_argument("video")
    p.add_argument("--noise-db", type=float, default=-35.0)
    p.add_argument("--min-silence", type=float, default=0.6)
    p.add_argument("--fillers", action="store_true", help="also cut um/uh (needs speech extra)")
    p.add_argument(
        "--also-cut",
        nargs="*",
        default=[],
        metavar="WORD",
        help='extra words to cut, e.g. --also-cut like basically',
    )
    p.add_argument("--out")
    p.set_defaults(fn=cmd_cut)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
