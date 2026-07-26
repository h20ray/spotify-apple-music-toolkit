"""Apple Music track search, cache, and batch processing."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from toolkit.core import ensure_all_folders, http_get
from toolkit.core.constants import (
    APPLE_SCORE_EXCELLENT,
    APPLE_SCORE_GOOD,
    APPLE_SCORE_MINIMUM,
    CACHE_SAVE_INTERVAL,
    DEFAULT_USER_AGENT,
    MAX_RETRY_ATTEMPTS,
    RATE_LIMIT_DELAY,
    TIMEOUT_API_SHORT,
)
from toolkit.playlists.apple_music.cloud import get_apple_developer_token
from toolkit.playlists.apple_music.scoring import score_track_candidate
from toolkit.playlists.apple_music.state import (
    CACHE_FILE,
    LEGACY_CACHE_FILE,
    SEARCH_CACHE,
    console,
    logger,
)
from toolkit.playlists.parser import generate_search_queries, verify_track_match


def ensure_folders() -> None:
    """Ensure project source and export directories exist."""
    ensure_all_folders()


def load_search_cache():
    """Load local search cache from .cache/ directory (with fallback to legacy cache) and evict invalid entries."""
    global SEARCH_CACHE
    target_path = CACHE_FILE if os.path.exists(CACHE_FILE) else (LEGACY_CACHE_FILE if os.path.exists(LEGACY_CACHE_FILE) else None)

    if target_path:
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)

            sanitized = {}
            for song_key, item in loaded.items():
                if item and isinstance(item, dict):
                    t_name = (item.get('trackName') or '').lower()
                    a_name = (item.get('artistName') or '').lower()
                    if verify_track_match(song_key, t_name, a_name):
                        sanitized[song_key] = item
            SEARCH_CACHE = sanitized
        except (OSError, json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed loading Apple Music search cache: {e}")
            SEARCH_CACHE = {}


def save_search_cache():
    """Save search cache to disk in .cache/ folder (persisting matched Apple Music track details and URLs)."""
    ensure_folders()
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        valid_cache = {k: v for k, v in SEARCH_CACHE.items() if v and isinstance(v, dict)}
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(valid_cache, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning(f"Failed saving Apple Music search cache: {e}")

def clear_search_cache_for_songs(songs=None):
    """Clear cached search results for specific songs or entire cache."""
    global SEARCH_CACHE
    if songs:
        for song in songs:
            SEARCH_CACHE.pop(song, None)
    else:
        SEARCH_CACHE = {}
    save_search_cache()

def search_apple_music_track(song_line, is_trim_retry=False):
    """
    Search track using multi-tier architecture with 429 rate limit backoff:
    1. Local Search Cache
    2. iTunes Search API (itunes.apple.com) with Early-Exit for high confidence matches (score >= 60.0)
    3. Apple Catalog API (amp-api.music.apple.com)
    4. Deezer API (metadata fallback)
    """
    if song_line in SEARCH_CACHE:
        return SEARCH_CACHE[song_line]

    user_wants_remix = "remix" in song_line.lower()
    user_wants_live = "live" in song_line.lower()

    queries = generate_search_queries(song_line)
    best_candidate = None
    best_score = 0.0

    # Step 1: iTunes Public Search API with Early-Exit and 429 Backoff
    url_itunes = "https://itunes.apple.com/search"
    for search_term in queries:
        params_itunes = {"term": search_term, "media": "music", "entity": "song", "limit": 10}
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                time.sleep(RATE_LIMIT_DELAY)
                resp = http_get(url_itunes, params=params_itunes, timeout=TIMEOUT_API_SHORT)
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    if results:
                        scored = []
                        for item in results:
                            s = score_track_candidate(item, song_line, user_wants_remix, user_wants_live)
                            scored.append(
                                (
                                    s,
                                    {
                                        "trackId": item.get("trackId", 0),
                                        "trackName": item.get("trackName", ""),
                                        "artistName": item.get("artistName", ""),
                                        "collectionName": item.get("collectionName", ""),
                                        "trackTimeMillis": item.get("trackTimeMillis", 0),
                                        "trackViewUrl": item.get("trackViewUrl", ""),
                                    },
                                )
                            )
                        scored.sort(key=lambda x: x[0], reverse=True)
                        if scored[0][0] > best_score:
                            best_score = scored[0][0]
                            best_candidate = scored[0][1]

                        if best_score >= APPLE_SCORE_EXCELLENT:
                            SEARCH_CACHE[song_line] = best_candidate
                            return best_candidate
                    break
                if resp.status_code == 429:
                    time.sleep(1.5 * (attempt + 1))
                else:
                    break
            except (OSError, ValueError, KeyError) as e:
                logger.debug(f"iTunes search attempt failed: {e}")
                time.sleep(0.3)

    if best_candidate and best_score >= APPLE_SCORE_EXCELLENT:
        SEARCH_CACHE[song_line] = best_candidate
        return best_candidate

    # Step 2: Official Apple Music Catalog Web API
    dev_token = get_apple_developer_token()
    if dev_token:
        headers_amp = {
            "Authorization": f"Bearer {dev_token}",
            "Origin": "https://music.apple.com",
            "Referer": "https://music.apple.com/"
        }
        url_amp = "https://amp-api.music.apple.com/v1/catalog/us/search"
        for search_term in queries:
            params_amp = {"term": search_term, "types": "songs", "limit": 10}
            for attempt in range(3):
                try:
                    time.sleep(RATE_LIMIT_DELAY)
                    resp = http_get(url_amp, params=params_amp, headers=headers_amp, timeout=TIMEOUT_API_SHORT)
                    if resp.status_code == 200:
                        data = resp.json().get("results", {}).get("songs", {}).get("data", [])
                        if data:
                            scored = []
                            for item in data:
                                attr = item.get("attributes", {})
                                s = score_track_candidate(item, song_line, user_wants_remix, user_wants_live)
                                raw_url = attr.get("url", "")
                                clean_url = raw_url.split("&uo=")[0] if raw_url else ""

                                scored.append(
                                    (
                                        s,
                                        {
                                            "trackId": item.get("id", 0),
                                            "trackName": attr.get("name", ""),
                                            "artistName": attr.get("artistName", ""),
                                            "collectionName": attr.get("albumName", ""),
                                            "trackTimeMillis": attr.get("durationInMillis", 0),
                                            "trackViewUrl": clean_url,
                                        },
                                    )
                                )

                            scored.sort(key=lambda x: x[0], reverse=True)
                            if scored[0][0] > best_score:
                                best_score = scored[0][0]
                                best_candidate = scored[0][1]

                            if best_score >= APPLE_SCORE_GOOD:
                                SEARCH_CACHE[song_line] = best_candidate
                                return best_candidate
                        break
                    if resp.status_code == 429:
                        time.sleep(1.5 * (attempt + 1))
                    else:
                        break
                except (OSError, ValueError, KeyError) as e:
                    logger.debug(f"AMP catalog search failed: {e}")

    if best_candidate and best_score > APPLE_SCORE_MINIMUM:
        SEARCH_CACHE[song_line] = best_candidate
        return best_candidate

    # Step 3: Fallback to Deezer API
    url_deezer = "https://api.deezer.com/search"
    headers_dz = {"User-Agent": DEFAULT_USER_AGENT}
    for search_term in queries:
        params_deezer = {"q": search_term}
        try:
            time.sleep(RATE_LIMIT_DELAY)
            resp_dz = http_get(url_deezer, params=params_deezer, headers=headers_dz, timeout=TIMEOUT_API_SHORT)
            if resp_dz.status_code == 200:
                data_dz = resp_dz.json()
                results_dz = data_dz.get("data", [])
                if results_dz:
                    scored_dz = []
                    for item in results_dz:
                        s = score_track_candidate(item, song_line, user_wants_remix, user_wants_live)
                        dz_title = item.get("title", "")
                        dz_artist = (
                            item.get("artist", {}).get("name", "") if isinstance(item.get("artist"), dict) else ""
                        )

                        scored_dz.append(
                            (
                                s,
                                {
                                    "trackId": 0,
                                    "trackName": dz_title,
                                    "artistName": dz_artist,
                                    "collectionName": (
                                        item.get("album", {}).get("title", "")
                                        if isinstance(item.get("album"), dict)
                                        else ""
                                    ),
                                    "trackTimeMillis": item.get("duration", 0) * 1000,
                                    "trackViewUrl": "",
                                },
                            )
                        )

                    scored_dz.sort(key=lambda x: x[0], reverse=True)
                    if scored_dz[0][0] > APPLE_SCORE_MINIMUM:
                        result = scored_dz[0][1]
                        SEARCH_CACHE[song_line] = result
                        return result
        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.debug(f"Deezer search failed: {e}")

    # Step 4: Smart Title Trimming Disambiguation
    if ' - ' in song_line and not is_trim_retry:
        parts = song_line.split(' - ', 1)
        artist, title = parts[0].strip(), parts[1].strip()
        words = title.split()
        if len(words) > 1:
            for i in range(len(words) - 1, 0, -1):
                sub_title = ' '.join(words[:i])
                sub_query = f"{artist} - {sub_title}"
                res = search_apple_music_track(sub_query, is_trim_retry=True)
                if res:
                    SEARCH_CACHE[song_line] = res
                    return res

            for i in range(1, len(words)):
                sub_title = ' '.join(words[i:])
                sub_query = f"{artist} - {sub_title}"
                res = search_apple_music_track(sub_query, is_trim_retry=True)
                if res:
                    SEARCH_CACHE[song_line] = res
                    return res

    SEARCH_CACHE[song_line] = None
    return None

def process_track_batch(songs, progress=None, task=None):
    """
    Search Apple Music tracks using controlled execution
    with adaptive throttling, early-exit optimization, and graceful Ctrl+C cache flushing.
    """
    load_search_cache()
    results_map = {}

    try:
        for i, song in enumerate(songs, 1):
            item = search_apple_music_track(song)
            results_map[song] = item

            if progress is not None and task is not None:
                if item:
                    status = f"-> [bold green]Found:[/bold green] [white]{item.get('trackName')}[/white]"
                else:
                    status = "-> [dim yellow]Not Found[/dim yellow]"
                progress.console.print(f"Searching [bold cyan]{song}[/bold cyan] {status}")
                progress.update(task, description=f"[dim]Processing ({i}/{len(songs)})[/dim]")
                progress.advance(task)

            if i % CACHE_SAVE_INTERVAL == 0:
                save_search_cache()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Process interrupted by user (Ctrl+C). Saving current search progress to cache...[/bold yellow]")
        save_search_cache()
        raise
    finally:
        save_search_cache()

    return results_map

