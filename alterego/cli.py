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


def cmd_devices(_args: argparse.Namespace) -> None:
    from .recorder import list_devices

    print(list_devices())
    print('Use the names in quotes above, e.g. --camera "HD WebCam".')


def cmd_record(args: argparse.Namespace) -> None:
    from .recorder import record

    record(
        camera=args.camera,
        mic=args.mic,
        screen=args.screen,
        out_stem=args.name,
    )


def cmd_preview(args: argparse.Namespace) -> None:
    """Live webcam preview of the disguise — press N for a new random
    seed, S to print the current one, Q to quit. Use this to *choose*
    your alter ego before you ever record."""
    import cv2
    import numpy as np

    from .disguise import DisguiseProfile, apply_disguise
    from .faces import FaceLandmarker, LandmarkSmoother

    capture = cv2.VideoCapture(args.camera_index)
    if not capture.isOpened():
        raise SystemExit(f"No webcam at index {args.camera_index}.")

    seed = args.seed
    profile = DisguiseProfile.from_seed(seed, args.strength)
    landmarker = FaceLandmarker()
    smoother = LandmarkSmoother()
    print(f"seed={seed} | N = new seed, S = show seed, Q = quit")

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
        if key == ord("s"):
            print(f"current seed: {seed} (strength {args.strength})")

    capture.release()
    cv2.destroyAllWindows()
    landmarker.close()


def cmd_disguise(args: argparse.Namespace) -> None:
    from .disguise import process_video

    out = args.out or _default_out(args.video, "alterego")
    process_video(args.video, out, seed=args.seed, strength=args.strength)


def cmd_enhance(args: argparse.Namespace) -> None:
    from .enhance import process_video

    out = args.out or _default_out(args.video, "graded")
    process_video(args.video, out)


def cmd_cut(args: argparse.Namespace) -> None:
    from .cuts import process_video

    out = args.out or _default_out(args.video, "tight")
    process_video(args.video, out, noise_db=args.noise_db, min_silence=args.min_silence)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="alterego",
        description="Terminal content studio: record, disguise, enhance, cut.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="list cameras and microphones").set_defaults(
        fn=cmd_devices
    )

    p = sub.add_parser("record", help="record webcam and/or screen until Enter")
    p.add_argument("--camera", help='camera name from `alterego devices`')
    p.add_argument("--mic", help='microphone name from `alterego devices`')
    p.add_argument("--screen", action="store_true", help="also record the screen")
    p.add_argument("--name", default="take", help="output filename stem")
    p.set_defaults(fn=cmd_record)

    p = sub.add_parser("preview", help="live disguise preview to pick a seed")
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--camera-index", type=int, default=0)
    p.set_defaults(fn=cmd_preview)

    p = sub.add_parser("disguise", help="apply your alter ego to a recording")
    p.add_argument("video")
    p.add_argument("--seed", type=int, required=True, help="your alter ego seed")
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--out")
    p.set_defaults(fn=cmd_disguise)

    p = sub.add_parser("enhance", help="fix lighting, white balance, color")
    p.add_argument("video")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_enhance)

    p = sub.add_parser("cut", help="remove silent gaps")
    p.add_argument("video")
    p.add_argument("--noise-db", type=float, default=-35.0)
    p.add_argument("--min-silence", type=float, default=0.6)
    p.add_argument("--out")
    p.set_defaults(fn=cmd_cut)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
