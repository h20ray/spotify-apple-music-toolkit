"""
Audio processing subpackage: tagging, artwork embedding, and lyrics downloading.
"""

from .tagger import process_audio_folder as tag_audio_folder, read_all_existing_metadata
from .artwork import process_album_art_fixer as fix_album_art
from .lyrics import sync_audio_library_lyrics, sync_playlist_text_lyrics

__all__ = [
    "tag_audio_folder",
    "read_all_existing_metadata",
    "fix_album_art",
    "sync_audio_library_lyrics",
    "sync_playlist_text_lyrics",
]
