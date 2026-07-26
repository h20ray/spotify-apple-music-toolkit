"""Tests for LRC formatting helpers."""

from toolkit.audio.lyrics import filter_best_lrc_item, format_lrc_with_headers


def test_format_lrc_adds_headers():
    raw = "[00:01.00]Hello world\n"
    out = format_lrc_with_headers(raw, "Title", "Artist", "Album")
    assert out.startswith("[ti:Title]")
    assert "[ar:Artist]" in out
    assert "[al:Album]" in out
    assert "[00:01.00]Hello world" in out


def test_format_lrc_empty():
    assert format_lrc_with_headers("", "T") == ""


def test_filter_best_prefers_synced_studio():
    results = [
        {"albumName": "Greatest Hits", "artistName": "Various", "syncedLyrics": "[00:01]x", "plainLyrics": None},
        {"albumName": "Studio Album", "artistName": "Band", "syncedLyrics": "[00:01]y", "plainLyrics": None},
    ]
    best = filter_best_lrc_item(results)
    assert best is not None
    assert best["albumName"] == "Studio Album"
