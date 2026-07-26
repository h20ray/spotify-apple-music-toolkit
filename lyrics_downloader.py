"""
Synced Lyrics Downloader Script.
Backward compatibility wrapper delegating to toolkit.audio.lyrics.
"""

from toolkit.audio.lyrics import (
    main,
    sync_audio_library_lyrics,
    sync_playlist_text_lyrics,
    search_single_lrc,
    fetch_synced_lrc,
    format_lrc_with_headers,
    save_lrc_file,
)

if __name__ == '__main__':
    main()
