"""
Core Configuration Module.
Centralizes paths, directory initialization, environment settings, and JSON keywords config loading.
"""

import os
import sys
import json
from dotenv import load_dotenv

# Force UTF-8 stdout encoding on Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

# Base project directory (root of repository)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG_DIR = os.path.join(BASE_DIR, "config")
KEYWORDS_FILE = os.path.join(CONFIG_DIR, "keywords.json")

PLAYLIST_SOURCES_DIR = os.path.join(BASE_DIR, "playlist_sources")
SOURCE_TEXT_FILES_DIR = os.path.join(PLAYLIST_SOURCES_DIR, "source_text_files")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
AUDIO_LIBRARY_DIR = os.path.join(BASE_DIR, "audio_library")
CACHE_DIR = os.path.join(BASE_DIR, ".cache")
PLAYLIST_EXPORTS_DIR = os.path.join(BASE_DIR, "playlist_exports")
EXPORT_APPLE_MUSIC_DIR = os.path.join(PLAYLIST_EXPORTS_DIR, "apple_music")
EXPORT_SPOTIFY_DIR = os.path.join(PLAYLIST_EXPORTS_DIR, "spotify")
EXPORT_LYRICS_DIR = os.path.join(PLAYLIST_EXPORTS_DIR, "lyrics")

SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
SPOTIPY_REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI', 'https://127.0.0.1:8888/callback')
APPLE_MUSIC_USER_TOKEN = os.getenv('APPLE_MUSIC_USER_TOKEN')
APPLE_MUSIC_DEVELOPER_TOKEN = os.getenv('APPLE_MUSIC_DEVELOPER_TOKEN')

DEFAULT_KEYWORDS = {
    "compilations": [
        "various artists", "compilation", "greatest hits", "best of", "top 100", "top 50",
        "essential", "dj mix", "now that's what i call", "summer hits", "soundtrack", "essential classics"
    ],
    "karaoke_and_tributes": [
        "karaoke", "tribute", "originally performed by", "in the style of", "cover version",
        "backing track", "tribute band", "sing-along", "instrumental version", "piano version",
        "tribute to", "originally by", "as made famous by", "sound-alike", "tribute artist",
        "instrumental", "cover", "guitar cover", "piano cover", "orchestral cover", "guitar tribute"
    ],
    "unwanted_versions": [
        "live", "acoustic", "instrumental", "tribute", "salute", "cover", "lullaby", "karaoke",
        "cast recording", "broadway"
    ],
    "unwanted_edits": [
        "remix", "edit", "mix", "dub", "refix", "flip", "rework", "re-work", "bootleg", "vip",
        "radio edit", "club mix", "extended", "slowed", "reverbed", "sped up", "tiktok version"
    ]
}

def ensure_all_folders():
    """Ensure all required project directories exist."""
    if os.path.exists(CACHE_DIR) and os.path.isfile(CACHE_DIR):
        try:
            token_data = None
            with open(CACHE_DIR, 'r', encoding='utf-8') as f:
                token_data = f.read()
            os.remove(CACHE_DIR)
            os.makedirs(CACHE_DIR, exist_ok=True)
            if token_data:
                with open(os.path.join(CACHE_DIR, "spotify_token.json"), 'w', encoding='utf-8') as f:
                    f.write(token_data)
        except Exception:
            pass

    folders = [
        CONFIG_DIR,
        CACHE_DIR,
        PLAYLIST_SOURCES_DIR,
        SOURCE_TEXT_FILES_DIR,
        REPORTS_DIR,
        AUDIO_LIBRARY_DIR,
        PLAYLIST_EXPORTS_DIR,
        EXPORT_APPLE_MUSIC_DIR,
        EXPORT_SPOTIFY_DIR,
        EXPORT_LYRICS_DIR,
    ]
    for folder in folders:
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)

def load_keywords_config():
    """
    Load keywords dictionary from config/keywords.json.
    Auto-creates default template if missing.
    """
    ensure_all_folders()

    if not os.path.exists(KEYWORDS_FILE):
        try:
            with open(KEYWORDS_FILE, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_KEYWORDS, f, ensure_ascii=False, indent=2)
        except Exception:
            return DEFAULT_KEYWORDS

    try:
        with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        merged = {}
        for key, default_val in DEFAULT_KEYWORDS.items():
            merged[key] = data.get(key, default_val)
        return merged
    except Exception:
        return DEFAULT_KEYWORDS

def get_all_txt_files():
    """
    Get all input song list text files.
    Prioritizes files in playlist_sources/source_text_files/, with fallback to playlist_sources/.
    Ignores generated execution reports (*_report.txt).
    """
    txt_files = []
    seen_names = set()

    # Priority 1: playlist_sources/source_text_files/
    if os.path.exists(SOURCE_TEXT_FILES_DIR):
        for f in sorted(os.listdir(SOURCE_TEXT_FILES_DIR)):
            if f.lower().endswith('.txt') and not f.lower().endswith('_report.txt'):
                fpath = os.path.join(SOURCE_TEXT_FILES_DIR, f)
                txt_files.append({'name': f, 'path': fpath, 'rel': 'playlist_sources/source_text_files/'})
                seen_names.add(f)

    # Priority 2: playlist_sources/ fallback
    if os.path.exists(PLAYLIST_SOURCES_DIR):
        for f in sorted(os.listdir(PLAYLIST_SOURCES_DIR)):
            if f.lower().endswith('.txt') and not f.lower().endswith('_report.txt') and f not in seen_names:
                fpath = os.path.join(PLAYLIST_SOURCES_DIR, f)
                if os.path.isfile(fpath):
                    txt_files.append({'name': f, 'path': fpath, 'rel': 'playlist_sources/'})

    return txt_files
