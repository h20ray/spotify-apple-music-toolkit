"""
Apple Music Playlist Creator Script.
Backward compatibility wrapper delegating to toolkit.playlists.apple_music.
"""

from toolkit.playlists.apple_music import (
    main,
    import_file_to_apple_music,
    search_apple_music_track,
    create_apple_music_cloud_playlist,
)

if __name__ == '__main__':
    main()
