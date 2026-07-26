"""
Audio processing subpackage: tagging, artwork embedding, and lyrics downloading.
"""

from .metadata import (
    AudioMetadata,
    read_audio_metadata,
    read_all_existing_metadata,
    read_audio_tags,
    read_local_audio_metadata,
)
from .tagger import process_audio_folder as tag_audio_folder
from .artwork import process_album_art_fixer as fix_album_art
from .lyrics import sync_audio_library_lyrics, sync_playlist_text_lyrics

__all__ = [
    "AudioMetadata",
    "read_audio_metadata",
    "read_all_existing_metadata",
    "read_audio_tags",
    "read_local_audio_metadata",
    "tag_audio_folder",
    "fix_album_art",
    "sync_audio_library_lyrics",
    "sync_playlist_text_lyrics",
]
