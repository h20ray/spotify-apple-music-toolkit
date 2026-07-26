"""Tests for unified metadata reader (no real audio required for missing-file path)."""

from toolkit.audio.metadata import AudioMetadata, read_audio_metadata, read_audio_tags, read_local_audio_metadata


def test_missing_file_returns_empty():
    meta = read_audio_metadata("definitely_missing_file_xyz.mp3")
    assert isinstance(meta, AudioMetadata)
    assert meta.title is None
    assert meta.has_cover is False


def test_wrappers_on_missing():
    d = read_audio_tags("nope.mp3")
    assert d["title"] is None
    t, a, al = read_local_audio_metadata("nope.m4a")
    assert t is None and a is None and al is None


def test_to_dict_keys():
    meta = AudioMetadata(title="T", artist="A", album="Al", genre="G", year="2020", bpm=120, has_cover=True)
    d = meta.to_dict()
    assert d["title"] == "T"
    assert d["bpm"] == 120
