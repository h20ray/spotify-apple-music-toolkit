"""Tests for album and Apple Music scoring."""

from toolkit.audio.artwork import score_album_quality
from toolkit.core.constants import (
    APPLE_SCORE_MISMATCH,
    QUALITY_SCORE_COMPILATION,
    QUALITY_SCORE_STUDIO_ALBUM,
)
from toolkit.playlists.apple_music import score_track_candidate


def test_score_album_studio():
    assert score_album_quality("Speak Now", "Taylor Swift") == QUALITY_SCORE_STUDIO_ALBUM


def test_score_album_compilation():
    assert score_album_quality("Greatest Hits", "Various Artists") == QUALITY_SCORE_COMPILATION


def test_score_track_mismatch():
    item = {
        "trackName": "Completely Different Song",
        "artistName": "Wrong Artist",
        "collectionName": "Album",
    }
    score = score_track_candidate(item, "Taylor Swift - Back to December", False, False)
    assert score == APPLE_SCORE_MISMATCH


def test_score_track_good_match():
    item = {
        "trackName": "Back to December",
        "artistName": "Taylor Swift",
        "collectionName": "Speak Now",
    }
    score = score_track_candidate(item, "Taylor Swift - Back to December", False, False)
    assert score > 15.0
