import os
import sys
import re
import time
import requests
import socket
import urllib3.util.connection as urllib_conn
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from dotenv import load_dotenv

# Force IPv4 socket resolution to prevent Apple CDN IPv6 403/429 rate limit blocks
def allowed_gai_family():
    return socket.AF_INET
urllib_conn.allowed_gai_family = allowed_gai_family

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt, Confirm

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
console = Console()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_FOLDER_NAME = "playlist_sources"
EXPORT_FOLDER_NAME = os.path.join("playlist_exports", "apple_music")

PLAYLIST_SOURCES_DIR = os.path.join(BASE_DIR, SOURCE_FOLDER_NAME)
EXPORT_APPLE_MUSIC_DIR = os.path.join(BASE_DIR, EXPORT_FOLDER_NAME)

RATE_LIMIT_LOCK = Lock()
LAST_REQUEST_TIME = [0.0]
CACHED_BEARER_TOKEN = [None]

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'AppleMusic/1.0 (Macintosh; Intel Mac OS X 10_15_7)'
]

UNWANTED_VERSION_KEYWORDS = [
    "live", "acoustic", "instrumental", "tribute", "salute",
    "cover", "lullaby", "karaoke", "cast recording", "broadway"
]

COMPILATION_KEYWORDS = [
    "compilation", "greatest hits", "best of", "top 100", "top 50", "essential",
    "various artists", "dj mix", "now that's what i call", "summer hits", "soundtrack"
]

def ensure_folders():
    """Ensure project source and export directories exist."""
    for folder in [PLAYLIST_SOURCES_DIR, EXPORT_APPLE_MUSIC_DIR]:
        if not os.path.exists(folder):
            os.makedirs(folder)

def clean_string(text):
    """Normalize string for comparison."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[\(\)\[\]\{\}\-\_\,\.\:\;\"\'\!\?\/\\]', ' ', text)
    return ' '.join(text.split())

def scan_playlist_files():
    """Scan playlist_sources directory for text files."""
    ensure_folders()
    files = [f for f in os.listdir(PLAYLIST_SOURCES_DIR) if f.lower().endswith('.txt')]
    files.sort()
    
    file_info_list = []
    for filename in files:
        full_path = os.path.join(PLAYLIST_SOURCES_DIR, filename)
        song_count = 0
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                c = line.strip()
                if c and not c.startswith("==="):
                    song_count += 1
        size_bytes = os.path.getsize(full_path)
        file_info_list.append({
            'filename': filename,
            'path': full_path,
            'song_count': song_count,
            'size': size_bytes
        })
    return file_info_list

def display_header():
    """Display clean Apple Music Playlist Creator header banner."""
    console.clear()
    banner_text = f"""[bold bright_red]APPLE MUSIC PLAYLIST CREATOR[/bold bright_red]
Convert text song lists into official Apple Music playlists (Direct Cloud API).
Source: [bold magenta]{SOURCE_FOLDER_NAME}/[/bold magenta]
Export Destination: [bold green]{EXPORT_FOLDER_NAME}/[/bold green]"""
    console.print(Panel(banner_text, border_style="red", expand=False))

def parse_songs(file_path):
    """Parse track titles from text file."""
    songs = []
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("==="):
                songs.append(cleaned)
    return songs

def generate_search_queries(song_line):
    """Smart parser to clean artist tags, typos, and unclosed brackets."""
    if ' - ' in song_line:
        parts = song_line.split(' - ', 1)
        title, artist = parts[0].strip(), parts[1].strip()
    else:
        title, artist = song_line.strip(), ""

    # Clean title
    title_clean = re.sub(r'[\(\[\{].*?[\)\]\}]', '', title).strip()
    title_clean = re.sub(r'[\(\[\{].*$', '', title_clean).strip()

    if title_clean.upper() == 'UNITED STATES OF PO':
        title_clean = 'United States of Pop'

    # Clean artist
    artist_clean = re.sub(r'[\(\[\{].*?[\)\]\}]', '', artist).strip()
    artist_clean = artist_clean.replace('/', ' ')
    if 'DEBT' in artist_clean.upper():
        artist_clean = artist_clean.replace('DEBT', 'DEPT')

    primary_artist = re.split(r'\s*(?:&|,|feat\.|ft\.|featuring|with|X)\s*', artist_clean, flags=re.IGNORECASE)[0].strip()

    queries = []
    if title and artist:
        queries.append(f"{title} {artist}".strip())
    if title_clean and artist_clean:
        queries.append(f"{title_clean} {artist_clean}".strip())
    if title_clean and primary_artist:
        queries.append(f"{title_clean} {primary_artist}".strip())
    if title_clean:
        queries.append(title_clean)

    seen = set()
    dedup_queries = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            dedup_queries.append(q)

    return title_clean or title, artist_clean or artist, dedup_queries

def score_track_candidate(item, query_title, query_artist, user_wants_remix, user_wants_live):
    """
    Score candidate track based on title, artist, studio album preference,
    and sanity rules (excluding live/remix/tribute tracks unless requested).
    """
    attr = item.get('attributes', {})
    track_name = attr.get('name') or item.get('trackName') or ''
    artist_name = attr.get('artistName') or item.get('artistName') or ''
    album_name = attr.get('albumName') or item.get('collectionName') or ''

    tn_clean = clean_string(track_name)
    an_clean = clean_string(artist_name)
    album_clean = clean_string(album_name)

    qt_clean = clean_string(query_title)
    qa_clean = clean_string(query_artist)

    score = 0.0

    # Title match
    if qt_clean in tn_clean or tn_clean in qt_clean:
        score += 40.0
    
    # Artist match
    if qa_clean and (qa_clean in an_clean or an_clean in qa_clean):
        score += 40.0

    # Avoid unwanted Live/Remix
    full_candidate_text = f"{tn_clean} {album_clean}"

    if not user_wants_remix and "remix" in full_candidate_text:
        score -= 40.0

    if not user_wants_live:
        for kw in ["live", "live at", "in concert", "live in"]:
            if kw in full_candidate_text:
                score -= 50.0
                break

    for kw in UNWANTED_VERSION_KEYWORDS:
        if kw in ["live", "acoustic", "instrumental"] and (user_wants_live or user_wants_remix):
            continue
        if kw in full_candidate_text:
            score -= 30.0

    # Studio Album vs Compilation
    for c_kw in COMPILATION_KEYWORDS:
        if c_kw in album_clean:
            score -= 15.0
            break

    # Exact match bonus
    if qt_clean == tn_clean:
        score += 15.0

    return score

def get_apple_developer_token():
    """Dynamically extract Apple Music Web Developer Bearer Token."""
    if CACHED_BEARER_TOKEN[0]:
        return CACHED_BEARER_TOKEN[0]

    dev_env = os.getenv("APPLE_MUSIC_DEVELOPER_TOKEN")
    if dev_env:
        CACHED_BEARER_TOKEN[0] = dev_env
        return dev_env

    try:
        url = 'https://music.apple.com/assets/index~f0647adb63.js'
        res = requests.get(url, headers={'User-Agent': USER_AGENTS[0]}, timeout=6)
        tokens = re.findall(r'ey[A-Za-z0-9\-_=]{20,}\.ey[A-Za-z0-9\-_=]{20,}\.[A-Za-z0-9\-_=]{20,}', res.text)
        if tokens:
            CACHED_BEARER_TOKEN[0] = tokens[0]
            return tokens[0]
    except Exception:
        pass

    return None

def create_apple_music_cloud_playlist(playlist_name, tracks, user_token):
    """
    Directly create playlist in user's Apple Music Cloud account via official Apple Music API.
    Zero third-party website dependency! Uses 2-step batch chunking strategy.
    """
    dev_token = get_apple_developer_token()
    if not dev_token:
        console.print("[bold red]Error: Unable to fetch Apple Music developer token.[/bold red]")
        return False

    url_create = "https://amp-api.music.apple.com/v1/me/library/playlists"
    headers = {
        "Authorization": f"Bearer {dev_token}",
        "Music-User-Token": user_token,
        "Content-Type": "application/json",
        "Origin": "https://music.apple.com",
        "Referer": "https://music.apple.com/"
    }

    payload_create = {
        "attributes": {
            "name": playlist_name,
            "description": "Generated by Spotify & Audio Toolkit"
        }
    }

    try:
        # Step 1: Create Playlist Container
        resp = requests.post(url_create, json=payload_create, headers=headers, timeout=10)
        if resp.status_code in [200, 201]:
            data = resp.json().get('data', [])
            if not data:
                console.print(f"[bold red]API Error:[/bold red] Could not parse created playlist ID.")
                return False

            playlist_id = data[0]['id']
            console.print(f"[bold cyan]Playlist Container Created! (ID: {playlist_id})[/bold cyan]")

            # Step 2: Add Tracks in Batches of 20
            track_ids = [item.get('trackId') for item in tracks if item.get('trackId')]
            all_track_objs = [{"id": str(tid), "type": "songs"} for tid in track_ids]

            url_add = f"https://amp-api.music.apple.com/v1/me/library/playlists/{playlist_id}/tracks"
            chunk_size = 20
            added_count = 0

            for i in range(0, len(all_track_objs), chunk_size):
                chunk = all_track_objs[i:i+chunk_size]
                time.sleep(0.15)
                resp_add = requests.post(url_add, json={"data": chunk}, headers=headers, timeout=10)
                if resp_add.status_code in [200, 201, 204]:
                    added_count += len(chunk)
                    console.print(f"[dim]Synced {added_count}/{len(all_track_objs)} tracks to Apple Music Cloud...[/dim]")
                else:
                    console.print(f"[bold yellow]Batch Add Notice ({resp_add.status_code}):[/bold yellow] {resp_add.text[:150]}")

            console.print(f"[bold green]✓ SUCCESS! Playlist '{playlist_name}' ({added_count} tracks) synced directly to your Apple Music Account![/bold green]")
            return True
        else:
            console.print(f"[bold yellow]Apple Music API Notice ({resp.status_code}):[/bold yellow] {resp.text[:200]}")
    except Exception as e:
        console.print(f"[bold red]API Exception:[/bold red] {e}")

    return False

def search_apple_music_track(song_line):
    """
    Search official Apple Music Catalog API with fallback to Deezer catalog.
    Returns official Apple Music Catalog Track IDs.
    """
    user_wants_remix = "remix" in song_line.lower()
    user_wants_live = "live" in song_line.lower()

    query_title, query_artist, queries = generate_search_queries(song_line)
    
    # Rate limit pause
    with RATE_LIMIT_LOCK:
        now = time.time()
        elapsed = now - LAST_REQUEST_TIME[0]
        if elapsed < 0.08:
            time.sleep(0.08 - elapsed)
        LAST_REQUEST_TIME[0] = time.time()

    dev_token = get_apple_developer_token()
    headers_amp = {
        "Authorization": f"Bearer {dev_token}",
        "Origin": "https://music.apple.com",
        "Referer": "https://music.apple.com/"
    }

    # Step 1: Official Apple Music Catalog API
    url_amp = "https://amp-api.music.apple.com/v1/catalog/us/search"
    for search_term in queries:
        params_amp = {"term": search_term, "types": "songs", "limit": 10}
        try:
            resp = requests.get(url_amp, params=params_amp, headers=headers_amp, timeout=6)
            if resp.status_code == 200:
                data = resp.json().get('results', {}).get('songs', {}).get('data', [])
                if data:
                    scored = []
                    for item in data:
                        attr = item.get('attributes', {})
                        s = score_track_candidate(item, query_title, query_artist, user_wants_remix, user_wants_live)
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
                    if scored[0][0] > 15.0:
                        return scored[0][1]
        except Exception:
            pass

    # Step 2: Fallback to Deezer API
    url_deezer = "https://api.deezer.com/search"
    headers_dz = {"User-Agent": USER_AGENTS[0]}
    for search_term in queries:
        params_deezer = {"q": search_term}
        try:
            resp_dz = requests.get(url_deezer, params=params_deezer, headers=headers_dz, timeout=6)
            if resp_dz.status_code == 200:
                data_dz = resp_dz.json()
                results_dz = data_dz.get('data', [])
                if results_dz:
                    scored_dz = []
                    for item in results_dz:
                        s = score_track_candidate(item, query_title, query_artist, user_wants_remix, user_wants_live)
                        dz_title = item.get('title', '')
                        dz_artist = item.get('artist', {}).get('name', '') if isinstance(item.get('artist'), dict) else ''

                        scored_dz.append((s, {
                            'trackId': 0, # Omit non-Apple ID for Cloud API payload
                            'trackName': dz_title,
                            'artistName': dz_artist,
                            'collectionName': item.get('album', {}).get('title', '') if isinstance(item.get('album'), dict) else '',
                            'trackTimeMillis': item.get('duration', 0) * 1000,
                            'trackViewUrl': ''
                        }))

                    scored_dz.sort(key=lambda x: x[0], reverse=True)
                    if scored_dz[0][0] > 15.0:
                        return scored_dz[0][1]
        except Exception:
            pass

    return None

def process_track_batch(songs, progress=None, task=None):
    """Search Apple Music tracks concurrently using 5 worker threads."""
    results_map = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_song = {executor.submit(search_apple_music_track, song): song for song in songs}
        for future in as_completed(future_to_song):
            song = future_to_song[future]
            try:
                item = future.result()
                results_map[song] = item
            except Exception:
                item = None
                results_map[song] = None
            
            if progress is not None and task is not None:
                if item:
                    status = f"-> [bold green]Found:[/bold green] [white]{item.get('trackName')}[/white]"
                else:
                    status = "-> [dim yellow]Not Found[/dim yellow]"
                progress.update(task, description=f"Searching [bold cyan]{song}[/bold cyan] {status}")
                progress.advance(task)

    return results_map

def export_apple_tsv(playlist_name, tracks, output_path):
    """Export official Apple Music native TSV Text Playlist format (.txt)."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("Name\tArtist\tComposer\tAlbum\tGenre\tSize\tTime\tDisc Number\tDisc Count\tTrack Number\tTrack Count\tYear\tDate Modified\tDate Added\tBit Rate\tSample Rate\tVolume Adjustment\tKind\tEqualizer\tComments\tPlay Count\tLast Played\tSkip Count\tLast Skipped\tMy Rating\tLocation\n")

        for item in tracks:
            title = item.get('trackName', '')
            artist = item.get('artistName', '')
            album = item.get('collectionName', '')
            duration_sec = int(item.get('trackTimeMillis', 0) / 1000)

            f.write(f"{title}\t{artist}\t\t{album}\t\t\t{duration_sec}\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\n")

def export_m3u8(playlist_name, tracks, output_path):
    """Export Apple Music compatible UTF-8 M3U playlist file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        f.write(f"#PLAYLIST:{playlist_name}\n\n")

        for item in tracks:
            artist = item.get('artistName', 'Unknown Artist')
            title = item.get('trackName', 'Unknown Title')
            duration_sec = int(item.get('trackTimeMillis', 0) / 1000)

            f.write(f"#EXTINF:{duration_sec},{artist} - {title}\n\n")

def export_apple_xml(playlist_name, tracks, output_path):
    """Export iTunes / Apple Music Library XML playlist file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n')
        f.write('<plist version="1.0">\n')
        f.write('<dict>\n')
        f.write('    <key>Major Version</key><integer>1</integer>\n')
        f.write('    <key>Minor Version</key><integer>1</integer>\n')
        f.write('    <key>Application Version</key><string>12.12.0</string>\n')
        f.write('    <key>Features</key><integer>5</integer>\n')
        f.write('    <key>Show Content Ratings</key><true/>\n')
        f.write('    <key>Tracks</key>\n')
        f.write('    <dict>\n')

        for idx, item in enumerate(tracks, 1):
            track_id = item.get('trackId', idx)
            title = item.get('trackName', '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            artist = item.get('artistName', '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            album = item.get('collectionName', '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            duration = item.get('trackTimeMillis', 0)

            f.write(f'        <key>{track_id}</key>\n')
            f.write('        <dict>\n')
            f.write(f'            <key>Track ID</key><integer>{track_id}</integer>\n')
            f.write(f'            <key>Name</key><string>{title}</string>\n')
            f.write(f'            <key>Artist</key><string>{artist}</string>\n')
            f.write(f'            <key>Album</key><string>{album}</string>\n')
            f.write(f'            <key>Total Time</key><integer>{duration}</integer>\n')
            f.write('        </dict>\n')

        f.write('    </dict>\n')
        f.write('    <key>Playlists</key>\n')
        f.write('    <array>\n')
        f.write('        <dict>\n')
        f.write(f'            <key>Name</key><string>{playlist_name.replace("&", "&amp;")}</string>\n')
        f.write('            <key>Playlist Items</key>\n')
        f.write('            <array>\n')
        for item in tracks:
            t_id = item.get('trackId', 0)
            f.write('                <dict>\n')
            f.write(f'                    <key>Track ID</key><integer>{t_id}</integer>\n')
            f.write('                </dict>\n')
        f.write('            </array>\n')
        f.write('        </dict>\n')
        f.write('    </array>\n')
        f.write('</dict>\n')
        f.write('</plist>\n')

def import_file_to_apple_music(file_info, custom_name=None):
    """Process text file and generate Apple Music playlist outputs in playlist_exports/apple_music/."""
    ensure_folders()
    filename = file_info['filename']
    file_path = file_info['path']
    songs = parse_songs(file_path)

    if not songs:
        console.print(f"[bold yellow]Notice: '{filename}' contains no songs. Skipping.[/bold yellow]")
        return None

    playlist_name = custom_name or os.path.splitext(filename)[0].replace('_', ' ').title()

    console.print(f"\n[bold green]Processing Apple Music Playlist:[/bold green] [bold white]{playlist_name}[/bold white] ({len(songs)} songs)")
    console.print("[dim]Applying track sanity scoring to select studio versions and filter out unwanted Live/Remix tracks...[/dim]\n")

    found_tracks = []
    not_found = []

    with Progress(
        SpinnerColumn(),
        TaskProgressColumn(),
        BarColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Initializing Multi-Threaded Search...", total=len(songs))
        batch_results = process_track_batch(songs, progress=progress, task=task)

        for song in songs:
            item = batch_results.get(song)
            if item:
                found_tracks.append((song, item))
            else:
                not_found.append(song)

    if not found_tracks:
        console.print(f"[bold red]Error: No matching songs found for '{playlist_name}'.[/bold red]")
        return None

    # Save output playlist files in playlist_exports/apple_music/
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

    # Check for direct Apple Music Cloud API creation token
    user_token = os.getenv("APPLE_MUSIC_USER_TOKEN")
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
