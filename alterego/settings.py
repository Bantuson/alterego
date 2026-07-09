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

The files are gitignored like passwords: anyone holding these knobs
can reproduce (or approximately invert) your disguise.

One identity or many: `alterego.json` is the default (your main alter
ego); the `identities/` folder holds NAMED personas — one file each —
for multi-character work: a solo creator playing three roles, or a
two-guest podcast where each guest brings their own file. Anywhere a
command accepts `--identity`, a bare name like `ceo` resolves to
`identities/ceo.json`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .disguise import DisguiseProfile

SETTINGS_FILE = Path("alterego.json")
IDENTITIES_DIR = Path("identities")


@dataclass
class Identity:
    profile: DisguiseProfile
    strength: float
    voice_seed: int


def resolve_identity_path(name: str | None) -> Path:
    """None -> the default file; a name -> identities/<name>.json;
    anything with a path separator or .json is used as a literal path."""
    if name is None:
        return SETTINGS_FILE
    if name.endswith(".json") or "/" in name or "\\" in name:
        return Path(name)
    return IDENTITIES_DIR / f"{name}.json"


def list_identities() -> list[str]:
    """Names of all saved personas (the default file is not listed)."""
    if not IDENTITIES_DIR.exists():
        return []
    return sorted(p.stem for p in IDENTITIES_DIR.glob("*.json"))


def save_identity(
    profile: DisguiseProfile,
    strength: float,
    voice_seed: int,
    name: str | None = None,
) -> Path:
    path = resolve_identity_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "profile": profile.to_dict(),
                "strength": strength,
                "voice_seed": voice_seed,
            },
            indent=2,
        )
    )
    return path


def load_identity(name: str | None = None) -> Identity | None:
    """Load an identity by name (or the default), migrating legacy
    seed-only files."""
    path = resolve_identity_path(name)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
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
