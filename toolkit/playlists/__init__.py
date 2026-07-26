"""
Playlist creation & export management for Spotify and Apple Music.
"""

from .spotify import main as run_spotify_playlist_creator, get_spotify_client
from .apple_music import main as run_apple_music_playlist_creator, create_apple_music_cloud_playlist
from .parser import parse_songs, pre_sanitize_song_line, scan_playlist_files
from .exporter import export_apple_tsv, export_m3u8, export_apple_xml

__all__ = [
    "run_spotify_playlist_creator",
    "get_spotify_client",
    "run_apple_music_playlist_creator",
    "create_apple_music_cloud_playlist",
    "parse_songs",
    "pre_sanitize_song_line",
    "scan_playlist_files",
    "export_apple_tsv",
    "export_m3u8",
    "export_apple_xml",
]
