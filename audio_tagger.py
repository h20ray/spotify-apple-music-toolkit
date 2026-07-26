"""
Audio Tagger Script.
Backward compatibility wrapper delegating to toolkit.audio.tagger.
"""

from toolkit.audio.tagger import (
    main,
    process_audio_folder,
    read_all_existing_metadata,
    select_best_original_track,
    detect_physical_bpm,
    calculate_mood,
    search_spotify_metadata,
    tag_mp3_file,
    tag_m4a_file,
    select_tagging_mode,
)

if __name__ == '__main__':
    main()

