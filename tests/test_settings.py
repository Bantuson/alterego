"""The saved identity must round-trip exactly — it IS the alter ego."""

import alterego.settings as settings


def test_identity_round_trips(tmp_path, monkeypatch):
    # Point the module at a temp file so tests never touch a real one.
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "alterego.json")
    settings.save_identity(seed=48213, strength=0.8)
    assert settings.load_identity() == (48213, 0.8)


def test_no_file_means_no_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "missing.json")
    assert settings.load_identity() is None
