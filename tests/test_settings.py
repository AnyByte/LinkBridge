"""Tests for linkbridge.settings."""

from pathlib import Path

from linkbridge.settings import Settings


def test_load_returns_defaults_when_file_missing(tmp_path: Path):
    settings_file = tmp_path / "settings.json"
    assert not settings_file.exists()

    s = Settings.load(settings_file)

    assert s.last_device is None
    assert s.start_stop_enabled is False


def test_save_and_load_round_trip(tmp_path: Path):
    settings_file = tmp_path / "subdir" / "settings.json"  # parent dir doesn't exist yet

    original = Settings(last_device="Circuit Tracks MIDI", start_stop_enabled=True)
    original.save(settings_file)

    assert settings_file.exists()

    loaded = Settings.load(settings_file)
    assert loaded.last_device == "Circuit Tracks MIDI"
    assert loaded.start_stop_enabled is True


def test_load_recovers_from_corrupt_json(tmp_path: Path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{ this is not json", encoding="utf-8")

    s = Settings.load(settings_file)

    assert s.last_device is None
    assert s.start_stop_enabled is False
    # The corrupt file should have been renamed out of the way.
    assert not settings_file.exists()
    corrupt_files = list(tmp_path.glob("settings.json.corrupt-*"))
    assert len(corrupt_files) == 1
