"""Apple Music Direct Cloud API Playlist Creator package."""
from __future__ import annotations

from toolkit.playlists.apple_music.cloud import (
    create_apple_music_cloud_playlist,
    get_apple_developer_token,
)
from toolkit.playlists.apple_music.menu import (
    import_file_to_apple_music,
    interactive_menu,
    main,
)
from toolkit.playlists.apple_music.scoring import score_track_candidate
from toolkit.playlists.apple_music.search import (
    process_track_batch,
    search_apple_music_track,
)

__all__ = [
    "create_apple_music_cloud_playlist",
    "get_apple_developer_token",
    "import_file_to_apple_music",
    "interactive_menu",
    "main",
    "process_track_batch",
    "score_track_candidate",
    "search_apple_music_track",
]
