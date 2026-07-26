"""Tests for mood derivation."""

from toolkit.audio.tagger import calculate_mood


def test_mood_energetic():
    assert calculate_mood("Dance Pop") == "Energetic"
    assert calculate_mood("EDM") == "Energetic"


def test_mood_chill():
    assert calculate_mood("Indie Folk") == "Chill & Melancholic"


def test_mood_smooth():
    assert calculate_mood("R&B") == "Smooth & Chill"


def test_mood_default_style():
    assert calculate_mood("Pop") == "Pop Style"
