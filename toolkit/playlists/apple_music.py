"""
Apple Music Direct Cloud API Playlist Creator Module.
Converts text song lists into official Apple Music playlists directly on your account.
Includes Track Sanity Engine, local search cache, multi-threaded search, and native TSV/M3U8/XML export.
Uses shared parser, dynamic JSON keyword configuration, and strict candidate track verification.
"""

import os
import sys
import re
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from toolkit.core import (
    PLAYLIST_SOURCES_DIR,
    SOURCE_TEXT_FILES_DIR,
    EXPORT_APPLE_MUSIC_DIR,
    CACHE_DIR,
    APPLE_MUSIC_USER_TOKEN,
    APPLE_MUSIC_DEVELOPER_TOKEN,
    http_get,
    http_post,
    ensure_all_folders,
)
from toolkit.playlists.parser import (
    parse_songs,
    clean_string,
    pre_sanitize_song_line,
    generate_search_queries,
    scan_playlist_files,
    verify_track_match,
    COMPILATION_KEYWORDS,
    KARAOKE_TRIBUTE_KEYWORDS,
    UNWANTED_VERSION_KEYWORDS,
    UNWANTED_EDIT_KEYWORDS,
)
from toolkit.playlists.exporter import (
    export_apple_tsv,
    export_m3u8,
    export_apple_xml,
)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt, Confirm

console = Console()

SOURCE_FOLDER_NAME = "playlist_sources"
EXPORT_FOLDER_NAME = os.path.join("playlist_exports", "apple_music")

RATE_LIMIT_LOCK = Lock()
LAST_REQUEST_TIME = [0.0]
CACHED_BEARER_TOKEN = [None]

CACHE_FILE = os.path.join(CACHE_DIR, "apple_music_search_cache.json")
LEGACY_CACHE_FILE = os.path.join(EXPORT_APPLE_MUSIC_DIR, "search_cache.json")
SEARCH_CACHE = {}

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'AppleMusic/1.0 (Macintosh; Intel Mac OS X 10_15_7)'
]

def ensure_folders():
    """Ensure project source and export directories exist."""
    ensure_all_folders()

def display_header():
    """Display clean Apple Music Playlist Creator header banner."""
    console.clear()
    banner_text = f"""[bold bright_red]APPLE MUSIC PLAYLIST CREATOR[/bold bright_red]
Convert text song lists into official Apple Music playlists (Direct Cloud API).
Source: [bold magenta]{SOURCE_FOLDER_NAME}/[/bold magenta]
Export Destination: [bold green]{EXPORT_FOLDER_NAME}/[/bold green]"""
    console.print(Panel(banner_text, border_style="red", expand=False))

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
        except Exception:
            SEARCH_CACHE = {}

def save_search_cache():
    """Save search cache to disk in .cache/ folder (persisting matched Apple Music track details and URLs)."""
    ensure_folders()
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        valid_cache = {k: v for k, v in SEARCH_CACHE.items() if v and isinstance(v, dict)}
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(valid_cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def clear_search_cache_for_songs(songs=None):
    """Clear cached search results for specific songs or entire cache."""
    global SEARCH_CACHE
    if songs:
        for song in songs:
            SEARCH_CACHE.pop(song, None)
    else:
        SEARCH_CACHE = {}
    save_search_cache()

def score_track_candidate(item, song_line, user_wants_remix, user_wants_live):
    """
    Score candidate track against query string with title/artist match verification.
    """
    attr = item.get('attributes', {})
    track_name = attr.get('name') or item.get('trackName') or ''
    artist_name = attr.get('artistName') or item.get('artistName') or ''
    album_name = attr.get('albumName') or item.get('collectionName') or ''

    # Strict artist & title disambiguation check (disqualifies mismatched songs like AB Three vs A.B.A. Three)
    if not verify_track_match(song_line, track_name, artist_name):
        return -500.0

    tn_clean = clean_string(track_name)
    an_clean = clean_string(artist_name)
    album_clean = clean_string(album_name)

    query_clean = clean_string(song_line)
    words = [w for w in query_clean.split() if len(w) > 1]

    score = 0.0
    matched_words = 0.0

    full_all_words = (tn_clean + " " + an_clean + " " + album_clean).split()
    for w in words:
        if w in tn_clean or w in an_clean or w in album_clean:
            matched_words += 1.0
        elif len(w) >= 4:
            w_stem = w[:4]
            if any(tw.startswith(w_stem) or w_stem in tw for tw in full_all_words if len(tw) >= 4):
                matched_words += 0.9

    if words:
        score += (matched_words / len(words)) * 60.0

    if ' - ' in song_line:
        parts = song_line.split(' - ', 1)
        p1_c = clean_string(parts[0])
        p2_c = clean_string(parts[1])

        p1_primary = clean_string(re.split(r'\s*(?:&|,|/|\\|\bfeat\.\b|\bft\.\b|\bfeaturing\b|\bwith\b|\bvs\.\b|\bvs\b|\bx\b)\s*', parts[0], flags=re.IGNORECASE)[0])
        p2_primary = clean_string(re.split(r'\s*(?:&|,|/|\\|\bfeat\.\b|\bft\.\b|\bfeaturing\b|\bwith\b|\bvs\.\b|\bvs\b|\bx\b)\s*', parts[1], flags=re.IGNORECASE)[0])

        p1_no_the = re.sub(r'^\bthe\b\s*', '', p1_c) if p1_c else ""
        p2_no_the = re.sub(r'^\bthe\b\s*', '', p2_c) if p2_c else ""
        an_no_the = re.sub(r'^\bthe\b\s*', '', an_clean) if an_clean else ""

        p1_primary_no_the = re.sub(r'^\bthe\b\s*', '', p1_primary) if p1_primary else ""
        p2_primary_no_the = re.sub(r'^\bthe\b\s*', '', p2_primary) if p2_primary else ""

        p1_words = [w for w in p1_c.split() if len(w) >= 3]
        p2_words = [w for w in p2_c.split() if len(w) >= 3]

        p1_all_words_in_art = bool(p1_words and all(w in an_clean or w in an_no_the for w in p1_words))
        p2_all_words_in_art = bool(p2_words and all(w in an_clean or w in an_no_the for w in p2_words))

        p1_in_art = bool(p1_c and p1_c in an_clean) or \
                    bool(p1_no_the and p1_no_the in an_no_the) or \
                    p1_all_words_in_art or \
                    bool(an_clean and len(an_clean) >= 3 and (an_clean in p1_c or an_no_the in p1_no_the)) or \
                    bool(p1_primary and len(p1_primary) >= 3 and (p1_primary in an_clean or p1_primary_no_the in an_no_the))

        p2_in_art = bool(p2_c and p2_c in an_clean) or \
                    bool(p2_no_the and p2_no_the in an_no_the) or \
                    p2_all_words_in_art or \
                    bool(an_clean and len(an_clean) >= 3 and (an_clean in p2_c or an_no_the in p2_no_the)) or \
                    bool(p2_primary and len(p2_primary) >= 3 and (p2_primary in an_clean or p2_primary_no_the in an_no_the))

        p1_in_title = bool(p1_c and (p1_c in tn_clean or tn_clean in p1_c))
        p2_in_title = bool(p2_c and (p2_c in tn_clean or tn_clean in p2_c))

        if not p2_in_title and p2_c and len(p2_c) >= 4:
            p2_stem = p2_c[:4]
            if any(tw.startswith(p2_stem) for tw in tn_clean.split() if len(tw) >= 4):
                p2_in_title = True

        if (p1_in_art and p2_in_title) or (p2_in_art and p1_in_title):
            score += 40.0
        elif p1_in_title or p2_in_title:
            score += 20.0

        if (p1_in_art and p2_c and tn_clean == p2_c) or (p2_in_art and p1_c and tn_clean == p1_c):
            score += 20.0

        if not p1_in_art and not p2_in_art:
            score -= 80.0

    full_candidate_all = f"{tn_clean} {an_clean} {album_clean}"

    user_wants_karaoke = "karaoke" in song_line.lower() or "tribute" in song_line.lower() or "cover" in song_line.lower()
    if not user_wants_karaoke:
        for kw in KARAOKE_TRIBUTE_KEYWORDS:
            if kw in full_candidate_all:
                score -= 100.0
                break

    full_candidate_text = f"{tn_clean} {album_clean}"

    if not user_wants_remix:
        for kw in UNWANTED_EDIT_KEYWORDS:
            if kw in full_candidate_text:
                score -= 40.0
                break

    if not user_wants_live:
        for kw in ["live", "live at", "in concert", "live in"]:
            if kw in full_candidate_text:
                score -= 50.0
                break

    user_wants_acoustic = "acoustic" in song_line.lower()
    if not user_wants_acoustic and "acoustic" in full_candidate_text:
        score -= 50.0

    for kw in UNWANTED_VERSION_KEYWORDS:
        if kw in ["live", "acoustic", "instrumental"] and (user_wants_live or user_wants_remix or user_wants_acoustic):
            continue
        if kw in full_candidate_text:
            score -= 30.0

    for c_kw in COMPILATION_KEYWORDS:
        if c_kw in album_clean:
            score -= 15.0
            break

    return score

def get_apple_developer_token():
    """Dynamically extract Apple Music Web Developer Bearer Token using network HTTP helper."""
    if CACHED_BEARER_TOKEN[0]:
        return CACHED_BEARER_TOKEN[0]

    dev_env = APPLE_MUSIC_DEVELOPER_TOKEN
    if dev_env:
        CACHED_BEARER_TOKEN[0] = dev_env
        return dev_env

    try:
        url = 'https://music.apple.com/assets/index~f0647adb63.js'
        res = http_get(url, headers={'User-Agent': USER_AGENTS[0]}, timeout=6)
        tokens = re.findall(r'ey[A-Za-z0-9\-_=]{20,}\.ey[A-Za-z0-9\-_=]{20,}\.[A-Za-z0-9\-_=]{20,}', res.text)
        if tokens:
            CACHED_BEARER_TOKEN[0] = tokens[0]
            return tokens[0]
    except Exception:
        pass

    return None

def create_apple_music_cloud_playlist(playlist_name, tracks, user_token=None):
    """
    Directly create playlist in user's Apple Music Cloud account via official Apple Music API.
    Zero third-party website dependency! Uses 2-step batch chunking strategy with rate-limit delays.
    """
    u_token = user_token or APPLE_MUSIC_USER_TOKEN
    if not u_token:
        console.print("[bold yellow]Notice: APPLE_MUSIC_USER_TOKEN not set in .env. Skipping direct Cloud Sync.[/bold yellow]")
        return False

    dev_token = get_apple_developer_token()
    if not dev_token:
        console.print("[bold red]Error: Unable to fetch Apple Music developer token.[/bold red]")
        return False

    url_create = "https://amp-api.music.apple.com/v1/me/library/playlists"
    headers = {
        "Authorization": f"Bearer {dev_token}",
        "Music-User-Token": u_token,
        "Content-Type": "application/json",
        "Origin": "https://music.apple.com",
        "Referer": "https://music.apple.com/"
    }

    payload_create = {
        "attributes": {
            "name": playlist_name,
            "description": "Generated by Spotify - Apple Music Toolkit"
        }
    }

    try:
        resp = http_post(url_create, json=payload_create, headers=headers, timeout=10)
        if resp.status_code in [200, 201]:
            data = resp.json().get('data', [])
            if not data:
                console.print(f"[bold red]API Error:[/bold red] Could not parse created playlist ID.")
                return False

            playlist_id = data[0]['id']
            console.print(f"[bold cyan]Playlist Container Created! (ID: {playlist_id})[/bold cyan]")

            track_ids = [item.get('trackId') for item in tracks if item.get('trackId')]
            all_track_objs = [{"id": str(tid), "type": "songs"} for tid in track_ids]

            url_add = f"https://amp-api.music.apple.com/v1/me/library/playlists/{playlist_id}/tracks"
            chunk_size = 20
            added_count = 0

            for i in range(0, len(all_track_objs), chunk_size):
                chunk = all_track_objs[i:i+chunk_size]
                time.sleep(0.3)

                for attempt in range(4):
                    resp_add = http_post(url_add, json={"data": chunk}, headers=headers, timeout=10)
                    if resp_add.status_code in [200, 201, 204]:
                        added_count += len(chunk)
                        console.print(f"[dim]Synced {added_count}/{len(all_track_objs)} tracks to Apple Music Cloud...[/dim]")
                        break
                    elif resp_add.status_code == 429:
                        time.sleep(2.0 * (attempt + 1))
                    else:
                        console.print(f"[bold yellow]Batch Add Notice ({resp_add.status_code}):[/bold yellow] {resp_add.text[:150]}")
                        break

            console.print(f"[bold green]✓ SUCCESS! Playlist '{playlist_name}' ({added_count} tracks) synced directly to your Apple Music Account![/bold green]")
            return True
        else:
            console.print(f"[bold yellow]Apple Music API Notice ({resp.status_code}):[/bold yellow] {resp.text[:200]}")
    except Exception as e:
        console.print(f"[bold red]API Exception:[/bold red] {e}")

    return False

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
        for attempt in range(4):
            try:
                time.sleep(0.1)
                resp = http_get(url_itunes, params=params_itunes, timeout=6)
                if resp.status_code == 200:
                    results = resp.json().get('results', [])
                    if results:
                        scored = []
                        for item in results:
                            s = score_track_candidate(item, song_line, user_wants_remix, user_wants_live)
                            scored.append((s, {
                                'trackId': item.get('trackId', 0),
                                'trackName': item.get('trackName', ''),
                                'artistName': item.get('artistName', ''),
                                'collectionName': item.get('collectionName', ''),
                                'trackTimeMillis': item.get('trackTimeMillis', 0),
                                'trackViewUrl': item.get('trackViewUrl', '')
                            }))
                        scored.sort(key=lambda x: x[0], reverse=True)
                        if scored[0][0] > best_score:
                            best_score = scored[0][0]
                            best_candidate = scored[0][1]

                        if best_score >= 75.0:
                            SEARCH_CACHE[song_line] = best_candidate
                            return best_candidate
                    break
                elif resp.status_code == 429:
                    time.sleep(1.5 * (attempt + 1))
                else:
                    break
            except Exception:
                time.sleep(0.3)

    if best_candidate and best_score >= 75.0:
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
                    time.sleep(0.1)
                    resp = http_get(url_amp, params=params_amp, headers=headers_amp, timeout=6)
                    if resp.status_code == 200:
                        data = resp.json().get('results', {}).get('songs', {}).get('data', [])
                        if data:
                            scored = []
                            for item in data:
                                attr = item.get('attributes', {})
                                s = score_track_candidate(item, song_line, user_wants_remix, user_wants_live)
                                raw_url = attr.get('url', '')
                                clean_url = raw_url.split('&uo=')[0] if raw_url else ''

                                scored.append((s, {
                                    'trackId': item.get('id', 0),
                                    'trackName': attr.get('name', ''),
                                    'artistName': attr.get('artistName', ''),
                                    'collectionName': attr.get('albumName', ''),
                                    'trackTimeMillis': attr.get('durationInMillis', 0),
                                    'trackViewUrl': clean_url
                                }))

                            scored.sort(key=lambda x: x[0], reverse=True)
                            if scored[0][0] > best_score:
                                best_score = scored[0][0]
                                best_candidate = scored[0][1]

                            if best_score >= 60.0:
                                SEARCH_CACHE[song_line] = best_candidate
                                return best_candidate
                        break
                    elif resp.status_code == 429:
                        time.sleep(1.5 * (attempt + 1))
                    else:
                        break
                except Exception:
                    pass

    if best_candidate and best_score > 15.0:
        SEARCH_CACHE[song_line] = best_candidate
        return best_candidate

    # Step 3: Fallback to Deezer API
    url_deezer = "https://api.deezer.com/search"
    headers_dz = {"User-Agent": USER_AGENTS[0]}
    for search_term in queries:
        params_deezer = {"q": search_term}
        try:
            time.sleep(0.1)
            resp_dz = http_get(url_deezer, params=params_deezer, headers=headers_dz, timeout=6)
            if resp_dz.status_code == 200:
                data_dz = resp_dz.json()
                results_dz = data_dz.get('data', [])
                if results_dz:
                    scored_dz = []
                    for item in results_dz:
                        s = score_track_candidate(item, song_line, user_wants_remix, user_wants_live)
                        dz_title = item.get('title', '')
                        dz_artist = item.get('artist', {}).get('name', '') if isinstance(item.get('artist'), dict) else ''

                        scored_dz.append((s, {
                            'trackId': 0,
                            'trackName': dz_title,
                            'artistName': dz_artist,
                            'collectionName': item.get('album', {}).get('title', '') if isinstance(item.get('album'), dict) else '',
                            'trackTimeMillis': item.get('duration', 0) * 1000,
                            'trackViewUrl': ''
                        }))

                    scored_dz.sort(key=lambda x: x[0], reverse=True)
                    if scored_dz[0][0] > 15.0:
                        result = scored_dz[0][1]
                        SEARCH_CACHE[song_line] = result
                        return result
        except Exception:
            pass

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

            if i % 5 == 0:
                save_search_cache()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Process interrupted by user (Ctrl+C). Saving current search progress to cache...[/bold yellow]")
        save_search_cache()
        raise
    finally:
        save_search_cache()

    return results_map

def import_file_to_apple_music(file_info, custom_name=None, auto_resume=False):
    """Process text file and generate Apple Music playlist outputs in playlist_exports/apple_music/."""
    ensure_folders()
    filename = file_info['filename']
    file_path = file_info['path']
    raw_songs = parse_songs(file_path)

    if not raw_songs:
        console.print(f"[bold yellow]Notice: '{filename}' contains no songs. Skipping.[/bold yellow]")
        return None

    cleaned_songs = [pre_sanitize_song_line(s) for s in raw_songs if pre_sanitize_song_line(s)]
    
    seen_keys = set()
    unique_songs = []
    for s in cleaned_songs:
        ckey = clean_string(s)
        if ckey and ckey not in seen_keys:
            seen_keys.add(ckey)
            unique_songs.append(s)

    def artist_sort_key(s):
        if ' - ' in s:
            parts = s.split(' - ', 1)
            return (clean_string(parts[0]), clean_string(parts[1]))
        return (clean_string(s), "")

    songs = sorted(unique_songs, key=artist_sort_key)
    dedup_removed = len(raw_songs) - len(songs)

    playlist_name = custom_name or os.path.splitext(filename)[0].replace('_', ' ').title()

    console.print(f"\n[bold green]Processing Apple Music Playlist:[/bold green] [bold white]{playlist_name}[/bold white] ({len(songs)} unique songs)")
    if dedup_removed > 0:
        console.print(f"[bold cyan]Pre-Sanitization Notice:[/bold cyan] Removed [bold green]{dedup_removed}[/bold green] duplicate/invalid entries ({len(raw_songs)} → {len(songs)} unique tracks).")
    console.print("[dim green]Sorted all tracks alphabetically by Artist Name.[/dim green]\n")

    load_search_cache()
    cached_count = sum(1 for song in songs if song in SEARCH_CACHE)

    if cached_count > 0 and not auto_resume:
        console.print(f"[bold yellow]Cache Notice:[/bold yellow] Found cached search results for [bold cyan]{cached_count}/{len(songs)}[/bold cyan] tracks.")
        console.print(" [bold cyan]1[/bold cyan] Resume (Use cached searches - Fast)")
        console.print(" [bold cyan]2[/bold cyan] Fresh Start (Clear cache & search all fresh from API)")
        cache_choice = Prompt.ask("\nSelect execution mode", choices=["1", "2"], default="1")

        if cache_choice == "2":
            clear_search_cache_for_songs(songs)
            console.print("[dim yellow]Cache cleared for this playlist. Starting 100% fresh API search...[/dim yellow]\n")
        else:
            console.print("[dim green]Resuming search using local cache...[/dim green]\n")

    console.print("[dim]Applying track sanity scoring to select studio versions and filter out unwanted Live/Remix tracks...[/dim]\n")

    found_tracks = []
    not_found = []

    try:
        with Progress(
            SpinnerColumn(),
            TaskProgressColumn(),
            BarColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Initializing Search...", total=len(songs))
            batch_results = process_track_batch(songs, progress=progress, task=task)
    except KeyboardInterrupt:
        console.print(f"[bold yellow]\nOperation aborted for '{playlist_name}'. All searched tracks saved to cache.[/bold yellow]")
        return None

    for song in songs:
        item = batch_results.get(song)
        if item:
            found_tracks.append((song, item))
        else:
            not_found.append(song)

    if not found_tracks:
        console.print(f"[bold red]Error: No matching songs found for '{playlist_name}'.[/bold red]")
        return None

    base_output_name = os.path.splitext(filename)[0]
    tsv_path = os.path.join(EXPORT_APPLE_MUSIC_DIR, f"{base_output_name}_apple_playlist.txt")
    m3u8_path = os.path.join(EXPORT_APPLE_MUSIC_DIR, f"{base_output_name}_apple_music.m3u8")
    xml_path = os.path.join(EXPORT_APPLE_MUSIC_DIR, f"{base_output_name}_apple_music.xml")

    matched_items = [item for _, item in found_tracks]
    export_apple_tsv(playlist_name, matched_items, tsv_path)
    export_m3u8(playlist_name, matched_items, m3u8_path)
    export_apple_xml(playlist_name, matched_items, xml_path)

    table = Table(title=f"Apple Music Playlist Summary: {playlist_name}", border_style="cyan")
    table.add_column("Property", style="bold white")
    table.add_column("Details", style="bold green")

    match_pct = int(len(found_tracks) / len(songs) * 100)
    table.add_row("Total Songs Listed", str(len(songs)))
    table.add_row("Matched Tracks", f"{len(found_tracks)} ({match_pct}%)")
    table.add_row("Unmatched Songs", str(len(not_found)))
    table.add_row("Native TSV (.txt)", f"[bold green]{tsv_path}[/bold green]")
    table.add_row("Exported XML File", f"[bold yellow]{xml_path}[/bold yellow]")
    table.add_row("Exported M3U8 File", f"[bold yellow]{m3u8_path}[/bold yellow]")

    console.print(table)

    user_token = APPLE_MUSIC_USER_TOKEN
    if user_token:
        console.print("\n[bold cyan]Found APPLE_MUSIC_USER_TOKEN in .env! Syncing directly to Apple Music Cloud...[/bold cyan]")
        create_apple_music_cloud_playlist(playlist_name, matched_items, user_token)

    if not_found:
        console.print(Panel(
            "\n".join([f"- {item}" for item in not_found[:15]]) + (f"\n... and {len(not_found)-15} more" if len(not_found) > 15 else ""),
            title=f"Unmatched Songs ({len(not_found)})",
            border_style="yellow"
        ))

    console.print("\n[bold green]✓ Apple Music Playlist processing completed![/bold green]")
    console.print(f"[dim]Output Folder: [bold white]{EXPORT_FOLDER_NAME}/[/bold white][/dim]")

    return tsv_path

def list_files_table(file_info_list):
    """Display table of available playlist text files."""
    table = Table(title="Available Playlist Files", border_style="magenta", header_style="bold cyan")
    table.add_column("Index", style="bold yellow", justify="center")
    table.add_column("File Name", style="bold white")
    table.add_column("Song Count", justify="right", style="green")
    table.add_column("Size (KB)", justify="right", style="dim")

    for idx, info in enumerate(file_info_list, 1):
        size_kb = f"{info['size'] / 1024:.1f}"
        table.add_row(str(idx), info['filename'], str(info['song_count']), size_kb)

    console.print(table)

def interactive_menu():
    """Run interactive menu loop for Apple Music Playlist Creator."""
    while True:
        display_header()
        file_info_list = scan_playlist_files()

        console.print("[bold yellow]APPLE MUSIC PLAYLIST CREATOR MENU:[/bold yellow]")
        console.print(" [bold cyan]1[/bold cyan] View Available Text Playlist Files")
        console.print(" [bold cyan]2[/bold cyan] Select One File to Create Apple Music Playlist")
        console.print(" [bold cyan]3[/bold cyan] Create Playlists for All Files (Batch Mode)")
        console.print(" [bold cyan]4[/bold cyan] Direct Cloud Sync Setup (.env guide)")
        console.print(" [bold cyan]0[/bold cyan] Return to Main Menu")

        choice = Prompt.ask("\nSelect option", choices=["1", "2", "3", "4", "0"], default="1")

        if choice == "1":
            display_header()
            if not file_info_list:
                console.print(f"[bold yellow]No text files found in '{SOURCE_FOLDER_NAME}/'[/bold yellow]")
            else:
                list_files_table(file_info_list)
            Prompt.ask("\nPress Enter to return")

        elif choice == "2":
            display_header()
            if not file_info_list:
                console.print(f"[bold red]No text files found in '{SOURCE_FOLDER_NAME}/'.[/bold red]")
                Prompt.ask("\nPress Enter to return")
                continue

            list_files_table(file_info_list)
            valid_indices = [str(i) for i in range(1, len(file_info_list) + 1)]
            file_idx = Prompt.ask("\nSelect file index to import", choices=valid_indices)
            selected_file = file_info_list[int(file_idx) - 1]

            default_name = os.path.splitext(selected_file['filename'])[0].replace('_', ' ').title()
            custom_name = Prompt.ask("Apple Music Playlist Name", default=default_name)

            import_file_to_apple_music(selected_file, custom_name=custom_name)
            Prompt.ask("\nPress Enter to return")

        elif choice == "3":
            display_header()
            if not file_info_list:
                console.print(f"[bold red]No text files found in '{SOURCE_FOLDER_NAME}/'.[/bold red]")
                Prompt.ask("\nPress Enter to return")
                continue

            list_files_table(file_info_list)
            if Confirm.ask(f"\nCreate Apple Music playlists for all {len(file_info_list)} files?"):
                for info in file_info_list:
                    import_file_to_apple_music(info)
                console.print("\n[bold green]Batch Apple Music Playlist Creation Complete![/bold green]")

            Prompt.ask("\nPress Enter to return")

        elif choice == "4":
            display_header()
            info_text = f"""[bold yellow]DIRECT APPLE MUSIC CLOUD API CREATION (NO THIRD-PARTY WEBSITES)[/bold yellow]

Python can push playlists directly into your Apple Music account via official Apple Music Cloud API!

[bold green]Step-by-Step Setup (1-Time):[/bold green]
1. Open [bold cyan]https://music.apple.com[/bold cyan] in Chrome / Edge / Brave and log in.
2. Press [bold yellow]F12[/bold yellow] (DevTools) -> [bold yellow]Application[/bold yellow] tab -> [bold yellow]Cookies[/bold yellow] -> [bold cyan]https://music.apple.com[/bold cyan]
3. Copy the value of [bold white]media-user-token[/bold white].
4. Add it to your [bold white].env[/bold white] file:
   [bold magenta]APPLE_MUSIC_USER_TOKEN=your_copied_token_here[/bold magenta]

Once added, Python will automatically create playlists directly inside your Apple Music account!"""
            console.print(Panel(info_text, border_style="blue"))
            Prompt.ask("\nPress Enter to return")

        elif choice == "0":
            break

def main():
    ensure_folders()
    interactive_menu()

if __name__ == '__main__':
    main()
