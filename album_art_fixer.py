"""
Album Art Fixer Script.
Backward compatibility wrapper delegating to toolkit.audio.artwork.
"""

from toolkit.audio.artwork import (
    main,
    process_album_art_fixer,
    read_audio_tags,
    sanitize_search_query,
    score_album_quality,
    get_high_res_artwork_itunes,
    get_high_res_artwork_deezer,
    fetch_artwork_bytes,
    embed_artwork,
)

if __name__ == '__main__':
    main()
