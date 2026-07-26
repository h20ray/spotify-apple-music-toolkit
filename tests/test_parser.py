"""Tests for playlist parser helpers."""

from toolkit.playlists.parser import (
    clean_string,
    generate_search_queries,
    pre_sanitize_song_line,
    verify_artist_match,
    verify_title_match,
    verify_track_match,
)


def test_clean_string_strips_accents():
    assert clean_string("Beyoncé") == "beyonce"


def test_clean_string_expands_censor():
    assert "fuck" in clean_string("f**k")


def test_pre_sanitize_strips_track_number():
    assert pre_sanitize_song_line("01. Hello - Adele") == "Hello - Adele"


def test_pre_sanitize_strips_video_tag():
    result = pre_sanitize_song_line("Song [Official Video] - Artist")
    assert "Official" not in result


def test_verify_title_match_exact():
    assert verify_title_match("Back to December", "Back to December")


def test_verify_title_match_rejects_unrelated():
    assert not verify_title_match("Cahaya Bulan", "Huboan Pe Ho Tu Bulan")


def test_verify_artist_match_spacing():
    assert verify_artist_match("5 Romeo", "5Romeo")


def test_verify_track_match_artist_title():
    assert verify_track_match("Taylor Swift - Back to December", "Back to December", "Taylor Swift")


def test_generate_search_queries_contains_base():
    queries = generate_search_queries("Artist - Title")
    assert any("Artist" in q and "Title" in q for q in queries)
