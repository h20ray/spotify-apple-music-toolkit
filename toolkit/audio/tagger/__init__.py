"""Audio tagging package: Spotify metadata, BPM, mood, writers, processor."""
from __future__ import annotations

from toolkit.audio.metadata import read_all_existing_metadata
from toolkit.audio.tagger.bpm import detect_physical_bpm
from toolkit.audio.tagger.metadata_fetch import (
    get_spotify_client,
    search_spotify_metadata,
    select_best_original_track,
)
from toolkit.audio.tagger.mood import calculate_mood
from toolkit.audio.tagger.processor import main, process_audio_folder, select_tagging_mode
from toolkit.audio.tagger.writer import tag_m4a_file, tag_mp3_file

__all__ = [
    "calculate_mood",
    "detect_physical_bpm",
    "get_spotify_client",
    "main",
    "process_audio_folder",
    "read_all_existing_metadata",
    "search_spotify_metadata",
    "select_best_original_track",
    "select_tagging_mode",
    "tag_m4a_file",
    "tag_mp3_file",
]
