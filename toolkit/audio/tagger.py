"""
Audio Tagger Module.
Handles audio metadata tagging (ID3/MP4), physical tempo (BPM) calculation, and music mood derivation.
"""

from __future__ import annotations

import datetime
import json
import os
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any, Optional

import spotipy
from mutagen import MutagenError
from mutagen.id3 import APIC, COMM, ID3, ID3NoHeaderError, TALB, TBPM, TCON, TIT2, TMOO, TPE1
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table
from spotipy.oauth2 import SpotifyClientCredentials

from toolkit.audio.metadata import read_all_existing_metadata
from toolkit.core import (
    AUDIO_LIBRARY_DIR,
    CACHE_DIR,
    REPORTS_DIR,
    SPOTIPY_CLIENT_ID,
    SPOTIPY_CLIENT_SECRET,
    http_get,
)
from toolkit.core.constants import (
    DEFAULT_MAX_WORKERS,
    LIBROSA_DURATION_SECONDS,
    TIMEOUT_API_LONG,
)
from toolkit.core.logging import get_logger
from toolkit.playlists.parser import COMPILATION_KEYWORDS, pre_sanitize_song_line

warnings.filterwarnings("ignore")

console = Console()
STATUS_LOCK = Lock()
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
            album_type == 'compilation' or
            any(k in album_name_lower for k in COMPILATION_KEYWORDS) or
            'various' in primary_artist
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

def detect_physical_bpm(file_path: str) -> int:
    """Calculate exact physical song tempo (BPM) from audio signal."""
    try:
        import librosa

        y, sr = librosa.load(file_path, duration=LIBROSA_DURATION_SECONDS)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        return int(round(float(tempo[0] if hasattr(tempo, "__len__") else tempo)))
    except Exception as e:
        logger.warning(f"BPM detection failed for {file_path}: {e}")
        return 0


def calculate_mood(primary_genre: str = "Pop") -> str:
    """Derive clean text music mood style from genre."""
    genre_lower = primary_genre.lower()
    if any(k in genre_lower for k in ["dance", "edm", "house", "rock", "metal"]):
        return "Energetic"
    if any(k in genre_lower for k in ["indie", "folk", "acoustic", "bedroom", "chill"]):
        return "Chill & Melancholic"
    if any(k in genre_lower for k in ["r&b", "soul", "jazz", "lo-fi", "soft"]):
        return "Smooth & Chill"
    return f"{primary_genre} Style"


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


def tag_mp3_file(file_path: str, final_meta: dict[str, Any], write_cover: bool = True) -> bool:
    """Save audio tags to MP3 file."""
    try:
        try:
            audio = MP3(file_path, ID3=ID3)
        except ID3NoHeaderError:
            audio = MP3(file_path)
            audio.add_tags()

        if audio.tags is None:
            audio.add_tags()

        tags = audio.tags
        tags.add(TIT2(encoding=3, text=final_meta["title"]))
        tags.add(TPE1(encoding=3, text=final_meta["artist"]))
        tags.add(TALB(encoding=3, text=final_meta["album"]))
        tags.add(TCON(encoding=3, text=final_meta["genre"]))

        if final_meta["bpm"] > 0:
            tags.add(TBPM(encoding=3, text=str(final_meta["bpm"])))

        tags.add(TMOO(encoding=1, text=final_meta["mood"]))
        tags.add(COMM(encoding=1, lang="eng", desc="", text=f"Mood: {final_meta['mood']}"))

        if write_cover and final_meta["cover_data"]:
            tags.add(
                APIC(
                    encoding=0,
                    mime="image/jpeg",
                    type=3,
                    desc="Cover",
                    data=final_meta["cover_data"],
                )
            )

        audio.save(v2_version=3)
        return True
    except (MutagenError, OSError) as e:
        logger.warning(f"Failed tagging MP3 {file_path}: {e}")
        return False


def tag_m4a_file(file_path: str, final_meta: dict[str, Any], write_cover: bool = True) -> bool:
    """Save audio tags to M4A file."""
    try:
        audio = MP4(file_path)
        audio["\xa9nam"] = final_meta["title"]
        audio["\xa9ART"] = final_meta["artist"]
        audio["\xa9alb"] = final_meta["album"]
        audio["\xa9gen"] = final_meta["genre"]

        if final_meta["year"]:
            audio["\xa9day"] = final_meta["year"]

        if final_meta["bpm"] > 0:
            audio["tmpo"] = [final_meta["bpm"]]

        audio["----:com.apple.iTunes:MOOD"] = final_meta["mood"].encode("utf-8")
        audio["\xa9cmt"] = [f"Mood: {final_meta['mood']}"]

        if write_cover and final_meta["cover_data"]:
            audio["covr"] = [MP4Cover(final_meta["cover_data"], imageformat=MP4Cover.FORMAT_JPEG)]

        audio.save()
        return True
    except (MutagenError, OSError, KeyError, TypeError) as e:
        logger.warning(f"Failed tagging M4A {file_path}: {e}")
        return False

def select_tagging_mode():
    """Prompt user for Tagging Mode selection."""
    console.print("\n[bold yellow]TAG PROTECTION SETTINGS:[/bold yellow]")
    console.print(" [bold cyan]1[/bold cyan] [bold green]Safeguard Mode (Fill missing tags only - Protect existing tags)[/bold green] [Recommended]")
    console.print(" [bold cyan]2[/bold cyan] Overwrite Mode (Replace all tags with Spotify data)")
    
    choice = Prompt.ask("\nSelect Mode", choices=["1", "2"], default="1")
    return choice

def _process_single_tagger_worker(fname, folder_path, mode, sp, thread_slot, progress, master_task, worker_status):
    """Worker function for tagging individual audio files concurrently."""
    file_path = os.path.join(folder_path, fname)
    file_base = os.path.splitext(fname)[0]

    existing = read_all_existing_metadata(file_path)
    query = f"{existing['title']} {existing['artist']}".strip() if (existing['title'] and existing['artist']) else file_base.replace('_', ' ')
    query = pre_sanitize_song_line(query)

    with STATUS_LOCK:
        worker_status[thread_slot] = f"[bold cyan]Thread #{thread_slot+1:02d}[/bold cyan] Tagging: [white]{query[:50]}[/white]"

    try:
        bpm_val = existing['bpm'] or detect_physical_bpm(file_path)
        sp_meta = search_spotify_metadata(sp, query)
        
        if not sp_meta:
            sp_meta = {
                'title': existing['title'] or file_base,
                'artist': existing['artist'] or "Unknown Artist",
                'album': existing['album'] or "Unknown Album",
                'genre': existing['genre'] or "Pop",
                'year': existing['year'] or "",
                'mood': calculate_mood(existing['genre'] or "Pop"),
                'cover_data': None
            }

        if mode == "1":
            final_title = existing['title'] or sp_meta['title']
            final_artist = existing['artist'] or sp_meta['artist']
            final_album = existing['album'] or sp_meta['album']
            final_genre = existing['genre'] or sp_meta['genre']
            final_year = existing['year'] or sp_meta['year']
            final_mood = sp_meta['mood']
            write_cover = not existing['has_cover']
            action_desc = "Protected Existing Tags"
        else:
            final_title = sp_meta['title']
            final_artist = sp_meta['artist']
            final_album = sp_meta['album']
            final_genre = sp_meta['genre']
            final_year = sp_meta['year']
            final_mood = sp_meta['mood']
            write_cover = True
            action_desc = "Overwritten All"

        final_meta = {
            'title': final_title,
            'artist': final_artist,
            'album': final_album,
            'genre': final_genre,
            'year': final_year,
            'bpm': bpm_val,
            'mood': final_mood,
            'cover_data': sp_meta['cover_data']
        }

        success = False
        if fname.lower().endswith('.mp3'):
            success = tag_mp3_file(file_path, final_meta, write_cover=write_cover)
        elif fname.lower().endswith('.m4a'):
            success = tag_m4a_file(file_path, final_meta, write_cover=write_cover)
        else:
            success = True

        return {
            'fname': fname,
            'title_artist': f"{final_title} - {final_artist}",
            'album': final_album,
            'bpm': bpm_val,
            'action_desc': action_desc,
            'success': success,
            'report': f"{fname} | {final_title} - {final_artist} | {final_album} | {final_genre} | {final_mood} | {bpm_val} BPM | {action_desc}" if success else f"{fname} | FAILED"
        }
    finally:
        with STATUS_LOCK:
            progress.advance(master_task)


def process_audio_folder(folder_path=AUDIO_LIBRARY_DIR, mode=None, max_workers=DEFAULT_MAX_WORKERS):
    """Multi-threaded scan of audio_library folder to calculate BPM and update audio metadata tags."""
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    audio_files = [
        f for f in os.listdir(folder_path)
        if f.lower().endswith(('.mp3', '.m4a', '.flac', '.aac'))
    ]

    if not audio_files:
        console.print(Panel(
            f"No audio files found in: [bold magenta]{folder_path}[/bold magenta]\n\n"
            "Place any .mp3 or .m4a files into this folder and run again.",
            title="Empty Audio Folder",
            border_style="yellow"
        ))
        return

    try:
        sp = get_spotify_client()
    except RuntimeError as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        logger.error(str(e))
        return

    console.print(
        f"\n[bold green]Found {len(audio_files)} audio file(s) | Multi-Threaded Engine ({max_workers} threads)...[/bold green]"
    )

    if not mode:
        mode = select_tagging_mode()

    results = []
    progress = Progress(
        SpinnerColumn(),
        TaskProgressColumn(),
        BarColumn(),
        TextColumn("[bold green]Tagging Progress ({task.completed}/{task.total} tracks)[/bold green]"),
        console=console
    )
    master_task = progress.add_task("Overall", total=len(audio_files))

    worker_status = [f"[dim]Thread #{i+1:02d}: Active...[/dim]" for i in range(max_workers)]

    def build_renderable():
        tbl = Table.grid(padding=(0, 0))
        tbl.add_column()
        tbl.add_row(progress)
        with STATUS_LOCK:
            for st in worker_status:
                tbl.add_row(st)
        return tbl

    with Live(build_renderable(), refresh_per_second=12, console=console) as live:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {}
            for idx, fname in enumerate(audio_files):
                thread_slot = idx % max_workers
                future = executor.submit(_process_single_tagger_worker, fname, folder_path, mode, sp, thread_slot, progress, master_task, worker_status)
                future_to_file[future] = fname

            for future in as_completed(future_to_file):
                res = future.result()
                results.append(res)
                live.update(build_renderable())

    results.sort(key=lambda x: x['fname'].lower())

    count_success = sum(1 for r in results if r['success'])
    count_failed = len(results) - count_success

    console.print()
    console.print(Panel(
        f"[bold white]Total Processed:[/bold white] {len(results)} files  |  "
        f"[bold green]Successfully Tagged:[/bold green] {count_success}  |  "
        f"[bold red]Failed:[/bold red] {count_failed}",
        title="[bold cyan]Multi-Threaded Audio Tagger Overview[/bold cyan]",
        border_style="cyan"
    ))

    try:
        if not os.path.exists(REPORTS_DIR):
            os.makedirs(REPORTS_DIR)
        report_path = os.path.join(REPORTS_DIR, "audio_tagging_report.txt")
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(report_path, "w", encoding="utf-8") as rf:
            rf.write(f"=== MULTI-THREADED AUDIO TAGGING REPORT ===\n")
            rf.write(f"Date & Time: {timestamp}\n")
            rf.write(f"Total Processed Tracks: {len(audio_files)}\n")
            rf.write(f"Worker Threads Used: {max_workers}\n\n")
            rf.write("FILE NAME | TITLE & ARTIST | ALBUM | GENRE | MOOD/STYLE | TEMPO (BPM) | STATUS\n")
            rf.write("-" * 80 + "\n")
            for r in results:
                rf.write(f"{r['report']}\n")
        
        console.print(f"[bold green]Full report saved to:[/bold green] [underline magenta]reports/audio_tagging_report.txt[/underline magenta]\n")
    except OSError as e:
        logger.warning(f"Could not write report file: {e}")
        console.print(f"[dim yellow]Notice: Could not write report file: {e}[/dim yellow]")


def main() -> None:
    console.clear()
    console.print(
        Panel(
            "[bold cyan]SMART MULTI-THREADED AUDIO TAGGER[/bold cyan]\n"
            "[bold green]Updates song tags, calculates song tempo (BPM), and embeds artwork via Multi-Threading.[/bold green]",
            border_style="green",
        )
    )

    try:
        workers_input = Prompt.ask(
            "\nSelect worker thread count (e.g. 5 to 20)",
            default=str(DEFAULT_MAX_WORKERS),
        )
        workers_val = int(workers_input)
    except (ValueError, TypeError):
        workers_val = DEFAULT_MAX_WORKERS

    process_audio_folder(AUDIO_LIBRARY_DIR, max_workers=workers_val)


if __name__ == "__main__":
    main()
