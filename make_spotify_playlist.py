"""
Legacy / Standalone Spotify Playlist Script.
Delegates to toolkit.playlists.spotify for client and search operations.
"""

import os
import sys
from toolkit.playlists.spotify import get_spotify_client, search_track, parse_songs
from toolkit.core import SOURCE_TEXT_FILES_DIR, PLAYLIST_SOURCES_DIR

def create_playlist_from_file(sp, user_id, playlist_name, file_path, public=True):
    """Creates a Spotify playlist from a given txt file."""
    songs = parse_songs(file_path)
    if not songs:
        print(f"No songs found in {file_path}.")
        return

    print(f"\nProcessing Playlist: '{playlist_name}' ({len(songs)} songs)...")
    
    track_uris = []
    found_count = 0
    not_found = []

    for idx, song in enumerate(songs, 1):
        track = search_track(sp, song)
        if track:
            track_uris.append(track['uri'])
            found_count += 1
            print(f"[{idx}/{len(songs)}] Found: {song} -> '{track['name']}' by {track['artists'][0]['name']}")
        else:
            not_found.append(song)
            print(f"[{idx}/{len(songs)}] Not Found: {song}")

    if not track_uris:
        print(f"No matching tracks were found on Spotify for '{playlist_name}'.")
        return

    print(f"\nCreating playlist '{playlist_name}' on Spotify...")
    playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=public)
    playlist_id = playlist['id']

    for i in range(0, len(track_uris), 100):
        batch = track_uris[i:i+100]
        sp.playlist_add_items(playlist_id, batch)

    print(f"\nSuccess! Playlist '{playlist_name}' created!")
    print(f"   Matches added: {found_count}/{len(songs)}")
    print(f"   Open in Spotify: {playlist['external_urls']['spotify']}")
    
    if not_found:
        print(f"   Could not locate {len(not_found)} tracks on Spotify:")
        for item in not_found:
            print(f"      - {item}")

def main():
    print("=" * 60)
    print("SPOTIFY AUTOMATIC PLAYLIST GENERATOR")
    print("=" * 60)

    sp = get_spotify_client()
    user_info = sp.current_user()
    user_id = user_info['id']
    display_name = user_info.get('display_name', user_id)
    print(f"Logged in as Spotify User: {display_name} ({user_id})\n")

    local_txt = os.path.join(SOURCE_TEXT_FILES_DIR, 'local_songs.txt')
    if not os.path.exists(local_txt):
        local_txt = os.path.join(PLAYLIST_SOURCES_DIR, 'local_songs.txt')

    intl_txt = os.path.join(SOURCE_TEXT_FILES_DIR, 'international_songs.txt')
    if not os.path.exists(intl_txt):
        intl_txt = os.path.join(PLAYLIST_SOURCES_DIR, 'international_songs.txt')

    if os.path.exists(local_txt):
        create_playlist_from_file(sp, user_id, "Local Songs (Indonesia)", local_txt, public=True)

    if os.path.exists(intl_txt):
        create_playlist_from_file(sp, user_id, "International Songs", intl_txt, public=True)

if __name__ == '__main__':
    main()
