"""Tests for playlist exporters."""

from toolkit.playlists.exporter import export_apple_tsv, export_apple_xml, export_m3u8


def test_export_apple_tsv(tmp_path, sample_tracks):
    out = tmp_path / "pl.txt"
    export_apple_tsv("Demo", sample_tracks, str(out))
    text = out.read_text(encoding="utf-8")
    assert "Name\tArtist" in text
    assert "Taylor Swift" in text
    assert "Back to December" in text


def test_export_m3u8(tmp_path, sample_tracks):
    out = tmp_path / "pl.m3u8"
    export_m3u8("Demo", sample_tracks, str(out))
    text = out.read_text(encoding="utf-8")
    assert "#EXTM3U" in text
    assert "#PLAYLIST:Demo" in text
    assert "Taylor Swift - Back to December" in text


def test_export_apple_xml(tmp_path, sample_tracks):
    out = tmp_path / "pl.xml"
    export_apple_xml("Demo", sample_tracks, str(out))
    text = out.read_text(encoding="utf-8")
    assert '<?xml version="1.0"' in text
    assert "Back to December" in text
    assert "<key>Name</key><string>Demo</string>" in text or "Demo" in text
