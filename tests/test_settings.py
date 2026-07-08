"""The saved identity must round-trip exactly — it IS the alter ego.

The file format grew from {"seed": N} to explicit knobs + voice_seed.
The migration test is the most important one here: an update must
never change a face someone has already published with.
"""

import json

import alterego.settings as settings
from alterego.disguise import DisguiseProfile


def use_tmp_file(tmp_path, monkeypatch):
    path = tmp_path / "alterego.json"
    monkeypatch.setattr(settings, "SETTINGS_FILE", path)
    return path


def test_identity_round_trips(tmp_path, monkeypatch):
    use_tmp_file(tmp_path, monkeypatch)
    profile = DisguiseProfile.from_seed(48213)
    settings.save_identity(profile, strength=0.8, voice_seed=999)

    loaded = settings.load_identity()
    assert loaded.profile == DisguiseProfile.from_dict(profile.to_dict())
    assert loaded.strength == 0.8
    assert loaded.voice_seed == 999


def test_legacy_seed_file_produces_the_same_face_as_before(tmp_path, monkeypatch):
    path = use_tmp_file(tmp_path, monkeypatch)
    path.write_text(json.dumps({"seed": 90719, "strength": 1.0}))

    loaded = settings.load_identity()
    # Exactly what the old code computed — published faces must not move.
    assert loaded.profile == DisguiseProfile.from_seed(90719, 1.0)
    # The seed doubles as the voice seed, as it always did.
    assert loaded.voice_seed == 90719


def test_no_file_means_no_identity(tmp_path, monkeypatch):
    use_tmp_file(tmp_path, monkeypatch)
    assert settings.load_identity() is None
