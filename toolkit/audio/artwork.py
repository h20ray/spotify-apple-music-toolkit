"""
Album Art Fixer Module.
Searches and embeds high-resolution (1000x1000+) studio cover art using iTunes, Deezer, Spotify, and MusicBrainz APIs.
Includes studio album quality scoring to filter out low-quality compilations.
"""

import os
import sys
import re
import time
import random
import logging
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import datetime

from toolkit.core import (
    AUDIO_LIBRARY_DIR,
    REPORTS_DIR,
    SPOTIPY_CLIENT_ID,
    SPOTIPY_CLIENT_SECRET,
    http_get,
)
from toolkit.playlists.parser import COMPILATION_KEYWORDS, pre_sanitize_song_line

warnings.filterwarnings("ignore")

import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.flac import FLAC, Picture

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.live import Live
from rich.prompt import Prompt

console = Console()
STATUS_LOCK = Lock()

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'iTunes/12.12.0 (Windows; Microsoft Windows 10 x64)'
]

def get_random_agent_headers():
    return {'User-Agent': random.choice(USER_AGENTS)}

def read_audio_tags(file_path):
    """Read Title, Artist, Album, and existing Cover status from local audio file."""
    f_lower = file_path.lower()
    info = {'title': None, 'artist': None, 'album': None, 'has_cover': False}

    if f_lower.endswith('.mp3'):
        try:
            audio = MP3(file_path, ID3=ID3)
            if audio.tags:
                if 'TIT2' in audio.tags and audio.tags['TIT2'].text:
                    info['title'] = str(audio.tags['TIT2'].text[0]).strip()
                if 'TPE1' in audio.tags and audio.tags['TPE1'].text:
                    info['artist'] = str(audio.tags['TPE1'].text[0]).strip()
                if 'TALB' in audio.tags and audio.tags['TALB'].text:
                    info['album'] = str(audio.tags['TALB'].text[0]).strip()
                info['has_cover'] = any(k.startswith('APIC') for k in audio.tags.keys())
        except Exception:
            pass

    elif f_lower.endswith('.m4a'):
        try:
            audio = MP4(file_path)
            if '\xa9nam' in audio and audio['\xa9nam']:
                info['title'] = str(audio['\xa9nam'][0]).strip()
            if '\xa9ART' in audio and audio['\xa9ART']:
                info['artist'] = str(audio['\xa9ART'][0]).strip()
            if '\xa9alb' in audio and audio['\xa9alb']:
                info['album'] = str(audio['\xa9alb'][0]).strip()
            info['has_cover'] = ('covr' in audio and bool(audio['covr']))
        except Exception:
            pass

    elif f_lower.endswith('.flac'):
        try:
            audio = FLAC(file_path)
            if 'title' in audio and audio['title']:
                info['title'] = str(audio['title'][0]).strip()
            if 'artist' in audio and audio['artist']:
                info['artist'] = str(audio['artist'][0]).strip()
            if 'album' in audio and audio['album']:
                info['album'] = str(audio['album'][0]).strip()
            info['has_cover'] = bool(audio.pictures)
        except Exception:
            pass

    return info

def sanitize_search_query(title, artist, filename_fallback=""):
    """Build clean search query from tags or filename using shared pre-sanitization."""
    if title and artist:
        t_clean = re.sub(r'[\(\[\{].*?[\)\]\}]', '', title).strip()
        a_clean = re.sub(r'[\(\[\{].*?[\)\]\}]', '', artist).strip()
        return pre_sanitize_song_line(f"{a_clean} {t_clean}".strip())
    
    base_name = os.path.splitext(filename_fallback)[0]
    base_clean = base_name.replace('_', ' ')
    base_clean = re.sub(r'^\d+[\.\-\s]+', '', base_clean)
    base_clean = re.sub(r'[\(\[\{].*?[\)\]\}]', '', base_clean).strip()
    return pre_sanitize_song_line(base_clean)

def score_album_quality(album_name, artist_name=""):
    """
    Quality scoring engine to prioritize official Studio Albums over Compilations and Soundtracks.
    Higher score indicates higher studio quality confidence.
    """
    if not album_name:
        return 10

    alb_lower = album_name.lower()
    art_lower = artist_name.lower()

    if any(k in alb_lower for k in COMPILATION_KEYWORDS) or 'various' in art_lower:
        return 5
    elif 'deluxe' in alb_lower or 'remaster' in alb_lower or 'expanded' in alb_lower:
        return 80
    elif 'single' in alb_lower or 'ep' in alb_lower:
        return 70
    else:
        return 100

def get_high_res_artwork_itunes(query, target_album=None):
    """
    Fetch high-res studio cover art URL via iTunes Search API with quality scoring.
    Upgrades low-res thumbnail URLs to uncompressed 1000x1000 image links.
    """
    url = "https://itunes.apple.com/search"
    params = {'term': query, 'media': 'music', 'entity': 'song', 'limit': 15}

    try:
        res = http_get(url, params=params, headers=get_random_agent_headers(), timeout=6)
        if res.status_code == 200:
            results = res.json().get('results', [])
            if not results:
                return None

            best_item = None
            best_score = -1

            for item in results:
                alb_name = item.get('collectionName', '')
                art_name = item.get('artistName', '')
                score = score_album_quality(alb_name, art_name)

                if target_album and alb_name and target_album.lower() in alb_name.lower():
                    score += 50

                if score > best_score:
                    best_score = score
                    best_item = item

            if best_item:
                raw_artwork = best_item.get('artworkUrl100', '')
                if raw_artwork:
                    # Upgrade thumbnail size from 100x100 to high-res 1000x1000
                    high_res_url = re.sub(r'/\d+x\d+bb\.', '/1000x1000bb.', raw_artwork)
                    return high_res_url
    except Exception:
        pass

    return None

def get_high_res_artwork_deezer(query):
    """Fallback high-res artwork search via Deezer API (1000x1000)."""
    url = "https://api.deezer.com/search"
    params = {'q': query, 'limit': 10}

    try:
        res = http_get(url, params=params, headers=get_random_agent_headers(), timeout=6)
        if res.status_code == 200:
            results = res.json().get('data', [])
            if not results:
                return None

            for item in results:
                album_obj = item.get('album', {})
                cover_xl = album_obj.get('cover_xl') or album_obj.get('cover_big')
                if cover_xl:
                    return cover_xl
    except Exception:
        pass

    return None

def fetch_artwork_bytes(artwork_url):
    """Download image bytes from URL with uncompressed fallback resolution tests."""
    if not artwork_url:
        return None

    test_urls = [artwork_url]
    if '1000x1000bb' in artwork_url:
        test_urls.append(artwork_url.replace('1000x1000bb', '800x800bb'))
        test_urls.append(artwork_url.replace('1000x1000bb', '600x600bb'))

    for test_url in test_urls:
        try:
            r = http_get(test_url, headers=get_random_agent_headers(), timeout=8)
            if r.status_code == 200 and len(r.content) > 5000:
                return r.content
        except Exception:
            pass

    return None

def embed_artwork_mp3(file_path, image_bytes):
    """Embed JPEG/PNG artwork into MP3 ID3 APIC tag."""
    try:
        try:
            audio = MP3(file_path, ID3=ID3)
        except ID3NoHeaderError:
            audio = MP3(file_path)
            audio.add_tags()

        if audio.tags is None:
            audio.add_tags()

        mime = 'image/png' if image_bytes.startswith(b'\x89PNG') else 'image/jpeg'

        audio.tags.add(APIC(
            encoding=0,
            mime=mime,
            type=3,
            desc='Cover',
            data=image_bytes
        ))
        audio.save(v2_version=3)
        return True
    except Exception:
        return False

def embed_artwork_m4a(file_path, image_bytes):
    """Embed cover art into M4A covr atom tag."""
    try:
        audio = MP4(file_path)
        img_format = MP4Cover.FORMAT_PNG if image_bytes.startswith(b'\x89PNG') else MP4Cover.FORMAT_JPEG
        audio['covr'] = [MP4Cover(image_bytes, imageformat=img_format)]
        audio.save()
        return True
    except Exception:
        return False

def embed_artwork_flac(file_path, image_bytes):
    """Embed cover art into FLAC picture block."""
    try:
        audio = FLAC(file_path)
        picture = Picture()
        picture.type = 3
        picture.mime = 'image/png' if image_bytes.startswith(b'\x89PNG') else 'image/jpeg'
        picture.desc = 'Cover'
        picture.data = image_bytes
        audio.clear_pictures()
        audio.add_picture(picture)
        audio.save()
        return True
    except Exception:
        return False

def embed_artwork(file_path, image_bytes):
    """Generic wrapper to embed artwork into MP3, M4A, or FLAC."""
    f_lower = file_path.lower()
    if f_lower.endswith('.mp3'):
        return embed_artwork_mp3(file_path, image_bytes)
    elif f_lower.endswith('.m4a'):
        return embed_artwork_m4a(file_path, image_bytes)
    elif f_lower.endswith('.flac'):
        return embed_artwork_flac(file_path, image_bytes)
    return False

def _process_single_artwork_worker(fname, folder_path, thread_slot, progress, master_task, worker_status):
    """Worker function for fixing artwork concurrently for a single audio file."""
    file_path = os.path.join(folder_path, fname)
    info = read_audio_tags(file_path)
    query = sanitize_search_query(info['title'], info['artist'], fname)

    with STATUS_LOCK:
        worker_status[thread_slot] = f"[bold cyan]Thread #{thread_slot+1:02d}[/bold cyan] Searching Art: [white]{query[:50]}[/white]"

    try:
        art_url = get_high_res_artwork_itunes(query, info['album'])
        source_label = "iTunes API (1000x1000)"

        if not art_url:
            art_url = get_high_res_artwork_deezer(query)
            source_label = "Deezer API (High-Res)"

        if not art_url:
            return {
                'fname': fname,
                'query': query,
                'source': "Not Found",
                'success': False,
                'report': f"{fname} | {query} | Not Found"
            }

        img_bytes = fetch_artwork_bytes(art_url)
        if not img_bytes:
            return {
                'fname': fname,
                'query': query,
                'source': f"{source_label} (Fetch Error)",
                'success': False,
                'report': f"{fname} | {query} | Fetch Error"
            }

        success = embed_artwork(file_path, img_bytes)
        return {
            'fname': fname,
            'query': query,
            'source': source_label,
            'success': success,
            'report': f"{fname} | {query} | {source_label} | Embedded ({len(img_bytes)//1024} KB)" if success else f"{fname} | {query} | Embedding Failed"
        }
    finally:
        progress.advance(master_task)

def process_album_art_fixer(folder_path=AUDIO_LIBRARY_DIR, max_workers=10):
    """Multi-threaded scan of audio_library folder to download and embed high-res cover artwork."""
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    audio_files = [
        f for f in os.listdir(folder_path)
        if f.lower().endswith(('.mp3', '.m4a', '.flac', '.aac'))
    ]

    if not audio_files:
        console.print(Panel(
            f"No audio files found in: [bold magenta]{folder_path}[/bold magenta]\n\n"
            "Place any .mp3, .m4a, or .flac files into this folder and run again.",
            title="Empty Audio Folder",
            border_style="yellow"
        ))
        return

    console.print(f"\n[bold green]Found {len(audio_files)} audio file(s) | Multi-Threaded Cover Art Fixer ({max_workers} threads)...[/bold green]")

    results = []
    progress = Progress(
        SpinnerColumn(),
        TaskProgressColumn(),
        BarColumn(),
        TextColumn("[bold green]Artwork Progress ({task.completed}/{task.total} files)[/bold green]"),
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
                future = executor.submit(_process_single_artwork_worker, fname, folder_path, thread_slot, progress, master_task, worker_status)
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
        f"[bold green]High-Res Artwork Embedded:[/bold green] {count_success}  |  "
        f"[bold red]Failed/Not Found:[/bold red] {count_failed}",
        title="[bold cyan]Multi-Threaded Album Art Fixer Overview[/bold cyan]",
        border_style="cyan"
    ))

    try:
        if not os.path.exists(REPORTS_DIR):
            os.makedirs(REPORTS_DIR)
        report_path = os.path.join(REPORTS_DIR, "album_art_fixer_report.txt")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(report_path, "w", encoding="utf-8") as rf:
            rf.write(f"=== MULTI-THREADED ALBUM ART FIXER REPORT ===\n")
            rf.write(f"Date & Time: {timestamp}\n")
            rf.write(f"Total Processed Tracks: {len(audio_files)}\n")
            rf.write(f"Worker Threads Used: {max_workers}\n\n")
            rf.write("FILE NAME | QUERY | ARTWORK SOURCE | STATUS\n")
            rf.write("-" * 80 + "\n")
            for r in results:
                rf.write(f"{r['report']}\n")

        console.print(f"[bold green]Full report saved to:[/bold green] [underline magenta]reports/album_art_fixer_report.txt[/underline magenta]\n")
    except Exception as e:
        console.print(f"[dim yellow]Notice: Could not write report file: {e}[/dim yellow]")

def main():
    console.clear()
    console.print(Panel(
        "[bold cyan]HIGH-RESOLUTION ALBUM ART FIXER (1000x1000)[/bold cyan]\n"
        "[bold green]Downloads & Embeds studio cover art into local MP3, M4A, and FLAC files.[/bold green]",
        border_style="green"
    ))

    try:
        workers_input = Prompt.ask("\nSelect worker thread count (e.g. 5 to 20)", default="10")
        workers_val = int(workers_input)
    except Exception:
        workers_val = 10

    process_album_art_fixer(AUDIO_LIBRARY_DIR, max_workers=workers_val)

if __name__ == '__main__':
    main()
