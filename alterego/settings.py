"""Persist the identity that must never be lost: your alter ego.

The identity file has grown up. Originally it stored a seed — one
number that generated the eight face knobs. But a seed is just one
of three ways to choose knobs (random roll, explicit design, or
matching a reference face), so the file now stores what is actually
fundamental:

  * the eight knob values themselves (the face),
  * a voice_seed (the voice — kept separate so redesigning your
    face never accidentally changes how you sound),
  * the warp strength.

Old files that contain only {"seed": ...} still load: the seed is
expanded to knobs exactly as before, so nobody's published alter ego
ever shifts because of a software update. That kind of migration —
new format, old files honored — is everyday professional work.

The file is gitignored like a password: anyone holding these knobs
can reproduce (or approximately invert) your disguise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .disguise import DisguiseProfile

SETTINGS_FILE = Path("alterego.json")


@dataclass
class Identity:
    profile: DisguiseProfile
    strength: float
    voice_seed: int


def save_identity(profile: DisguiseProfile, strength: float, voice_seed: int) -> Path:
    SETTINGS_FILE.write_text(
        json.dumps(
            {
                "profile": profile.to_dict(),
                "strength": strength,
                "voice_seed": voice_seed,
            },
            indent=2,
        )
    )
    return SETTINGS_FILE


def load_identity() -> Identity | None:
    """Load the saved identity, migrating legacy seed-only files."""
    if not SETTINGS_FILE.exists():
        return None
    data = json.loads(SETTINGS_FILE.read_text())
    strength = float(data.get("strength", 1.0))

    if "profile" in data:
        return Identity(
            profile=DisguiseProfile.from_dict(data["profile"]),
            strength=strength,
            voice_seed=int(data["voice_seed"]),
        )

    # Legacy format: {"seed": N}. Expand the seed to knobs exactly as
    # the old code did (strength baked in), and reuse it as the voice
    # seed — both match what the user has already published with.
    seed = int(data["seed"])
    return Identity(
        profile=DisguiseProfile.from_seed(seed, strength),
        strength=strength,
        voice_seed=seed,
    )
