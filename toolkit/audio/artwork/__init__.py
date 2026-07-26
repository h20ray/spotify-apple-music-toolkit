"""Album art fixer package: sources, embed, processor."""
from __future__ import annotations

from toolkit.audio.artwork.embed import embed_artwork
from toolkit.audio.artwork.processor import main, process_album_art_fixer
from toolkit.audio.artwork.sources import (
    fetch_artwork_bytes,
    get_high_res_artwork_deezer,
    get_high_res_artwork_itunes,
    sanitize_search_query,
    score_album_quality,
)
from toolkit.audio.metadata import read_audio_tags

__all__ = [
    "embed_artwork",
    "fetch_artwork_bytes",
    "get_high_res_artwork_deezer",
    "get_high_res_artwork_itunes",
    "main",
    "process_album_art_fixer",
    "read_audio_tags",
    "sanitize_search_query",
    "score_album_quality",
]
