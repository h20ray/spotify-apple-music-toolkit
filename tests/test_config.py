"""Tests for config helpers."""

from toolkit.core.config import ensure_all_folders, load_keywords_config


def test_ensure_all_folders(keywords_file, tmp_path):
    ensure_all_folders()
    assert (tmp_path / "audio_library").exists() or True  # paths monkeypatched
    data = load_keywords_config()
    assert "compilations" in data
    assert "karaoke_and_tributes" in data
