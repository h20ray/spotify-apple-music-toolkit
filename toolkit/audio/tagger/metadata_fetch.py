"""Spotify metadata search, cache, and studio-track selection."""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from toolkit.audio.tagger.mood import calculate_mood
from toolkit.core import (
    CACHE_DIR,
    SPOTIPY_CLIENT_ID,
    SPOTIPY_CLIENT_SECRET,
    http_get,
)
from toolkit.core.constants import TIMEOUT_API_LONG
from toolkit.core.logging import get_logger
from toolkit.playlists.parser import COMPILATION_KEYWORDS

logger = get_logger(__name__)

SPOTIFY_TAG_CACHE_FILE = os.path.join(CACHE_DIR, "spotify_tag_cache.json")
_SPOTIFY_TAG_CACHE: dict[str, Any] = {}
_SPOTIFY_TAG_CACHE_LOADED = False


def _load_spotify_tag_cache() -> None:
    global _SPOTIFY_TAG_CACHE, _SPOTIFY_TAG_CACHE_LOADED
    if _SPOTIFY_TAG_CACHE_LOADED:
        return
    _SPOTIFY_TAG_CACHE_LOADED = True
    if os.path.exists(SPOTIFY_TAG_CACHE_FILE):
        try:
            with open(SPOTIFY_TAG_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _SPOTIFY_TAG_CACHE = data
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed loading Spotify tag cache: {e}")
            _SPOTIFY_TAG_CACHE = {}


def _save_spotify_tag_cache() -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(SPOTIFY_TAG_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_SPOTIFY_TAG_CACHE, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning(f"Failed saving Spotify tag cache: {e}")


def get_spotify_client() -> spotipy.Spotify:
    """Authenticate with Spotify via API credentials."""
    if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET:
        raise RuntimeError("Missing SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET in .env configuration file.")

    auth_mgr = SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID, client_secret=SPOTIPY_CLIENT_SECRET)
    return spotipy.Spotify(client_credentials_manager=auth_mgr)


def select_best_original_track(items):
    """Prioritizes official Studio Albums over Compilations and Various Artists collections."""
    if not items:
        return None

    studio_albums = []
    singles = []
    others = []

    for track in items:
        album = track.get('album', {})
        album_name = album.get('name', '').strip()
        album_type = album.get('album_type', '').lower()
        artists = track.get('artists', [])
        primary_artist = artists[0]['name'].lower() if artists else ""

        album_name_lower = album_name.lower()
        is_compilation = (
            album_type == 'compilation'
            or any(k in album_name_lower for k in COMPILATION_KEYWORDS)
            or 'various' in primary_artist
        )

        if not is_compilation:
            if album_type == 'album':
                studio_albums.append(track)
            elif album_type == 'single':
                singles.append(track)
            else:
                others.append(track)
        else:
            others.append(track)

    if studio_albums:
        return studio_albums[0]
    elif singles:
        return singles[0]
    elif others:
        return others[0]
    return items[0]


def search_spotify_metadata(sp: spotipy.Spotify, query_text: str) -> Optional[dict[str, Any]]:
    """Fetch track details from Spotify API (with local cache)."""
    _load_spotify_tag_cache()
    cache_key = query_text.strip().lower()
    if cache_key in _SPOTIFY_TAG_CACHE:
        cached = dict(_SPOTIFY_TAG_CACHE[cache_key])
        cached["cover_data"] = None
        return cached

    try:
        res = sp.search(q=query_text, limit=5, type="track")
        items = res.get("tracks", {}).get("items", [])
        if not items:
            return None

        track = select_best_original_track(items)
        if not track:
            return None

        primary_genre = "Pop"
        artist_id = track["artists"][0]["id"]
        try:
            artist_info = sp.artist(artist_id)
            genres = artist_info.get("genres", [])
            if genres:
                primary_genre = genres[0].title()
        except spotipy.SpotifyException as e:
            logger.debug(f"Artist genre lookup failed: {e}")

        mood = calculate_mood(primary_genre)

        cover_data = None
        images = track.get("album", {}).get("images", [])
        if images:
            img_url = images[0]["url"]
            try:
                img_res = http_get(img_url, timeout=TIMEOUT_API_LONG)
                if img_res.status_code == 200:
                    cover_data = img_res.content
            except OSError as e:
                logger.debug(f"Cover download failed: {e}")
            except Exception as e:
                logger.debug(f"Cover download failed: {e}")

        year = ""
        release_date = track.get("album", {}).get("release_date", "")
        if release_date:
            year = release_date.split("-")[0]

        result = {
            "title": track["name"],
            "artist": ", ".join([a["name"] for a in track["artists"]]),
            "album": track["album"]["name"],
            "genre": primary_genre,
            "year": year,
            "mood": mood,
            "cover_data": cover_data,
        }
        # Cache serializable fields only
        _SPOTIFY_TAG_CACHE[cache_key] = {
            "title": result["title"],
            "artist": result["artist"],
            "album": result["album"],
            "genre": result["genre"],
            "year": result["year"],
            "mood": result["mood"],
        }
        _save_spotify_tag_cache()
        return result
    except spotipy.SpotifyException as e:
        logger.warning(f"Spotify search failed for '{query_text}': {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected Spotify metadata error for '{query_text}': {e}")
        return None
