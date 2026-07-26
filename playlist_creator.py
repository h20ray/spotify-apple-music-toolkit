"""
Spotify Playlist Creator Script.
Backward compatibility wrapper delegating to toolkit.playlists.spotify.
"""

from toolkit.playlists.spotify import (
    main,
    get_spotify_client,
    import_file_to_spotify,
    search_track,
)

if __name__ == '__main__':
    main()
