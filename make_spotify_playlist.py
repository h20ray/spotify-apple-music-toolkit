import sys
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

# Force UTF-8 stdout encoding on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables from .env file
load_dotenv()

# ==========================================
# CREDENTIALS & CONFIGURATION
# ==========================================
CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI', 'http://127.0.0.1:8888/callback')
SCOPE = 'playlist-modify-public playlist-modify-private'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYLIST_SOURCES_DIR = os.path.join(BASE_DIR, 'playlist_sources')

def get_spotify_client():
    """Authenticate and return Spotipy client instance using SpotifyOAuth."""
    print(f"Connecting to Spotify using Redirect URI: {REDIRECT_URI} ...")
    
    if not CLIENT_ID or not CLIENT_SECRET:
        print("❌ Error: SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET is missing from .env file!")
        sys.exit(0)
        
    auth_manager = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        open_browser=True
    )
    return spotipy.Spotify(auth_manager=auth_manager)

def load_songs_from_file(file_path):
    """Load song entries from a txt file."""
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return []
    
    songs = []
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("==="):
                songs.append(cleaned)
    return songs

def search_track(sp, song_line):
    """Search for a track on Spotify by 'Title - Artist' or query string."""
    if ' - ' in song_line:
        parts = song_line.split(' - ', 1)
        title, artist = parts[0].strip(), parts[1].strip()
        query = f"track:{title} artist:{artist}"
        try:
            results = sp.search(q=query, limit=1, type='track')
            items = results.get('tracks', {}).get('items', [])
            if items:
                return items[0]
        except Exception:
            pass
    
    try:
        results = sp.search(q=song_line, limit=1, type='track')
        items = results.get('tracks', {}).get('items', [])
        if items:
            return items[0]
    except Exception as e:
        print(f"   Search error for '{song_line}': {e}")
    
    return None

def create_playlist_from_file(sp, user_id, playlist_name, file_path, public=True):
    """Creates a Spotify playlist from a given txt file."""
    songs = load_songs_from_file(file_path)
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

    local_txt = os.path.join(PLAYLIST_SOURCES_DIR, 'local_songs.txt')
    intl_txt = os.path.join(PLAYLIST_SOURCES_DIR, 'international_songs.txt')

    if os.path.exists(local_txt):
        create_playlist_from_file(sp, user_id, "Local Songs (Indonesia)", local_txt, public=True)

    if os.path.exists(intl_txt):
        create_playlist_from_file(sp, user_id, "International Songs", intl_txt, public=True)

if __name__ == '__main__':
    main()
