"""Persist the one setting that must never be lost: your alter-ego seed.

The seed defines your public face. If it lives only in terminal
scrollback, one closed window ends your alter ego's career. So the
preview's "keep" key writes it to `alterego.json` in the project
folder, and `disguise` reads it back by default.

(A JSON file beats an environment variable or CLI flag here because
it survives reboots and is impossible to mistype.)
"""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS_FILE = Path("alterego.json")


def save_identity(seed: int, strength: float) -> Path:
    SETTINGS_FILE.write_text(
        json.dumps({"seed": seed, "strength": strength}, indent=2)
    )
    return SETTINGS_FILE


def load_identity() -> tuple[int, float] | None:
    """Return (seed, strength) or None if nothing was saved yet."""
    if not SETTINGS_FILE.exists():
        return None
    data = json.loads(SETTINGS_FILE.read_text())
    return int(data["seed"]), float(data.get("strength", 1.0))
