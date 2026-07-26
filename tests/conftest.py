"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sys

import pytest

# Ensure repo root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def sample_tracks():
    return [
        {
            "trackId": 1,
            "trackName": "Back to December",
            "artistName": "Taylor Swift",
            "collectionName": "Speak Now",
            "trackTimeMillis": 294000,
        },
        {
            "trackId": 2,
            "trackName": "360",
            "artistName": "Charli xcx",
            "collectionName": "Brat",
            "trackTimeMillis": 160000,
        },
    ]


@pytest.fixture
def keywords_file(tmp_path, monkeypatch):
    """Point keywords config at temp dir."""
    import toolkit.core.config as config

    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    keywords = cfg_dir / "keywords.json"
    monkeypatch.setattr(config, "CONFIG_DIR", str(cfg_dir))
    monkeypatch.setattr(config, "KEYWORDS_FILE", str(keywords))
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path / ".cache"))
    monkeypatch.setattr(config, "PLAYLIST_SOURCES_DIR", str(tmp_path / "playlist_sources"))
    monkeypatch.setattr(config, "SOURCE_TEXT_FILES_DIR", str(tmp_path / "playlist_sources" / "source_text_files"))
    monkeypatch.setattr(config, "REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(config, "AUDIO_LIBRARY_DIR", str(tmp_path / "audio_library"))
    monkeypatch.setattr(config, "PLAYLIST_EXPORTS_DIR", str(tmp_path / "playlist_exports"))
    monkeypatch.setattr(config, "EXPORT_APPLE_MUSIC_DIR", str(tmp_path / "playlist_exports" / "apple_music"))
    monkeypatch.setattr(config, "EXPORT_SPOTIFY_DIR", str(tmp_path / "playlist_exports" / "spotify"))
    monkeypatch.setattr(config, "EXPORT_LYRICS_DIR", str(tmp_path / "playlist_exports" / "lyrics"))
    return keywords
