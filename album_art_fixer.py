import os
import sys
import re
import time
import random
import logging
import warnings
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from dotenv import load_dotenv

# Suppress warnings
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

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
console = Console()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_FOLDER = os.path.join(BASE_DIR, "audio_library")
REPORT_DIR = os.path.join(BASE_DIR, "playlist_sources")

USER_AGENTS_POOL = [
    'iTunes/12.12.0 (Windows; N)',
    'iTunes/12.9.5 (Windows; N)',
    'AppleMusic/1.0 (Macintosh; Intel Mac OS X 10_15_7)',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
]

COMPILATION_KEYWORDS = [
    "compilation", "greatest hits", "direct hits", "best of", "top 100", "top 50", "top 40", "top 20", "top 10",
    "mega hits", "essential", "essentials", "various artists", "dj mix", "mixed", "now that's what i call",
    "summer hits", "today's hits", "party hits", "tribute", "salute", "karaoke", "workout", "gym", "playlist",
    "vol.", "volume", "soundtrack", "collection", "remixes", "pop hits", "rock hits", "emo pop punk",
    "rock anthems", "classics", "radio", "charts", "billboard", "grammy", "ultimate", "throwback",
    "retro", "gold", "platinum", "hits 20", "hits 19", "hits 18", "90s", "80s", "70s", "2000s", "2010s", "2020s"
]

UNWANTED_VERSION_KEYWORDS = [
    "live", "sofi stadium", "stadium", "acoustic", "instrumental", "remix", "remixes", "tribute", "salute",
    "cover", "lullaby", "burnt", "karaoke", "cast recording", "broadway", "blippi", "jazz salute"
]

RATE_LIMIT_LOCK = Lock()
LAST_REQUEST_TIME = [0.0]
STATUS_LOCK = Lock()

def get_random_agent_headers():
    """Get HTTP headers with rotating Agent string."""
    return {
        'User-Agent': random.choice(USER_AGENTS_POOL),
        'Accept': '*/*'
    }

def clean_title_for_search(t):
    """Strip all parenthesized, bracketed, or curly-bracketed descriptor tags for clean API searching."""
    if not t:
        return ""
    t = re.sub(r'[\(\[\{].*?[\)\]\}]', '', t)
    t = re.sub(r'(?:feat\.|ft\.|featuring).*$', '', t, flags=re.IGNORECASE)
    return ' '.join(t.split())

def get_primary_artist(artist_name):
    """Extract primary artist name before duet/feature delimiters."""
    if not artist_name:
        return ""
    art = re.split(r'\s*(?:&|,|feat\.|ft\.|featuring|with|X)\s*', artist_name, flags=re.IGNORECASE)[0]
    return art.strip()

def clean_text_normalized(text, strip_single_tags=False):
    """Normalize string by removing non-alphanumeric characters and lowercase."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', '', text)
    if strip_single_tags:
        text = re.sub(r'\b(?:single|ep|deluxe|version|edition)\b', '', text)
    return ' '.join(text.split())

def calculate_token_similarity(str1, str2):
    """Calculate token overlap similarity ratio between two strings (0.0 to 1.0)."""
    t1 = set(clean_text_normalized(str1).split())
    t2 = set(clean_text_normalized(str2).split())
    if not t1 or not t2:
        return 0.0
    intersection = t1.intersection(t2)
    union = t1.union(t2)
    return len(intersection) / float(len(union))

def read_audio_tags(file_path):
    """Read existing title, artist, album metadata from audio file."""
    f_lower = file_path.lower()
    meta = {
        'title': None,
        'artist': None,
        'album': None,
        'has_cover': False
    }

    if f_lower.endswith('.mp3'):
        try:
            audio = MP3(file_path, ID3=ID3)
            if audio.tags:
                if 'TIT2' in audio.tags and audio.tags['TIT2'].text:
                    meta['title'] = str(audio.tags['TIT2'].text[0]).strip()
                if 'TPE1' in audio.tags and audio.tags['TPE1'].text:
                    meta['artist'] = str(audio.tags['TPE1'].text[0]).strip()
                if 'TALB' in audio.tags and audio.tags['TALB'].text:
                    meta['album'] = str(audio.tags['TALB'].text[0]).strip()
                meta['has_cover'] = any(k.startswith('APIC') for k in audio.tags.keys())
        except Exception:
            pass
    elif f_lower.endswith('.m4a'):
        try:
            audio = MP4(file_path)
            if '\xa9nam' in audio and audio['\xa9nam']:
                meta['title'] = str(audio['\xa9nam'][0]).strip()
            if '\xa9ART' in audio and audio['\xa9ART']:
                meta['artist'] = str(audio['\xa9ART'][0]).strip()
            if '\xa9alb' in audio and audio['\xa9alb']:
                meta['album'] = str(audio['\xa9alb'][0]).strip()
            meta['has_cover'] = ('covr' in audio and bool(audio['covr']))
        except Exception:
            pass
    elif f_lower.endswith('.flac'):
        try:
            audio = FLAC(file_path)
            if 'title' in audio and audio['title']:
                meta['title'] = str(audio['title'][0]).strip()
            if 'artist' in audio and audio['artist']:
                meta['artist'] = str(audio['artist'][0]).strip()
            if 'album' in audio and audio['album']:
                meta['album'] = str(audio['album'][0]).strip()
            meta['has_cover'] = bool(audio.pictures)
        except Exception:
            pass

    filename = os.path.splitext(os.path.basename(file_path))[0]
    filename_clean = filename.replace('_', ' ').replace('-', ' - ')
    if ' - ' in filename_clean and (not meta['title'] or not meta['artist']):
        parts = filename_clean.split(' - ', 1)
        if not meta['artist']:
            meta['artist'] = parts[0].strip()
        if not meta['title']:
            meta['title'] = parts[1].strip()
    elif not meta['title']:
        meta['title'] = filename_clean.strip()

    return meta

def score_candidate(candidate_artist, candidate_title, candidate_album, coll_artist, target_artist, target_title, is_comp_type=False, strict_compilation_check=True):
    """Candidate scoring algorithm with exact title single bonus & version penalties."""
    target_artist_clean = clean_text_normalized(target_artist)
    target_primary_clean = clean_text_normalized(get_primary_artist(target_artist))
    target_title_clean = clean_text_normalized(clean_title_for_search(target_title))
    target_title_stripped = clean_text_normalized(clean_title_for_search(target_title), strip_single_tags=True)
    
    cand_artist_clean = clean_text_normalized(candidate_artist)
    cand_title_clean = clean_text_normalized(clean_title_for_search(candidate_title))
    cand_album_stripped = clean_text_normalized(candidate_album, strip_single_tags=True)
    coll_artist_clean = clean_text_normalized(coll_artist)

    raw_cand_album = (candidate_album or "").lower()
    raw_cand_title = (candidate_title or "").lower()

    score = 100.0

    # 1. Artist Match & Discard Check
    artist_sim = calculate_token_similarity(target_artist_clean, cand_artist_clean)
    if cand_artist_clean == target_artist_clean:
        score += 40
    elif target_primary_clean and target_primary_clean in cand_artist_clean:
        score += 35
    elif target_artist_clean in cand_artist_clean or cand_artist_clean in target_artist_clean:
        score += 25
    else:
        if artist_sim == 0.0 and target_primary_clean not in cand_artist_clean:
            score -= 200
        else:
            score += int(artist_sim * 30) - 30

    # 2. Track Title Match Score
    title_sim = calculate_token_similarity(target_title_clean, cand_title_clean)
    if cand_title_clean == target_title_clean:
        score += 40
    elif target_title_clean in cand_title_clean or cand_title_clean in target_title_clean:
        score += 25
    else:
        score += int(title_sim * 30) - 30

    # 3. Exact Title Album/Single Bonus (+60 pts) when single/album name matches track title
    if cand_album_stripped == target_title_stripped and not any(kw in raw_cand_album for kw in UNWANTED_VERSION_KEYWORDS):
        score += 60

    # 4. Penalize Live / Acoustic / Remix / Cover versions on raw unstripped strings
    for kw in UNWANTED_VERSION_KEYWORDS:
        if kw in raw_cand_album or kw in raw_cand_title:
            if kw not in target_title.lower():
                score -= 120

    is_compilation = False
    for kw in COMPILATION_KEYWORDS:
        if kw in raw_cand_album or kw in cand_artist_clean:
            is_compilation = True
            break

    if "various" in coll_artist_clean or "various" in cand_artist_clean:
        is_compilation = True

    if is_compilation or is_comp_type:
        cat_type = "Soundtrack/Compilation Fallback"
    elif "single" in raw_cand_album or cand_album_stripped == target_title_stripped:
        cat_type = "Single"
    else:
        cat_type = "Studio Album"

    if strict_compilation_check:
        if is_compilation or is_comp_type:
            score -= 150
        elif cat_type == "Single":
            score += 30
        else:
            score += 60  # Preference for Official Studio Album
    else:
        if is_compilation or is_comp_type:
            score += 20

    return score, cat_type

# --- PROVIDER 1: iTunes / Apple Music (Bypasses WAF blocks) ---
def search_itunes_provider(artist, title, strict=True):
    clean_t = clean_title_for_search(title)
    primary_art = get_primary_artist(artist)

    stages = [
        {"term": f"{artist} {clean_t}".strip(), "entity": "song"},
        {"term": f"{primary_art} {clean_t}".strip(), "entity": "song"},
        {"term": clean_t or title, "entity": "song"}
    ]

    endpoints = [
        "http://ax.itunes.apple.com/WebObjects/MZStoreServices.woa/wa/wsSearch",
        "https://itunes.apple.com/search"
    ]

    for params in stages:
        if not params["term"]:
            continue
        params["limit"] = 15
        params["country"] = "us"
        params["media"] = "music"

        with RATE_LIMIT_LOCK:
            now = time.time()
            if now - LAST_REQUEST_TIME[0] < 0.05:
                time.sleep(0.05)
            LAST_REQUEST_TIME[0] = time.time()

        for ep in endpoints:
            for attempt in range(2):
                try:
                    res = requests.get(ep, params=params, headers=get_random_agent_headers(), timeout=6)
                    if res.status_code == 200 and res.text.strip().startswith('{'):
                        results = res.json().get('results', [])
                        if results:
                            scored = []
                            for cand in results:
                                sc, cat_type = score_candidate(
                                    cand.get('artistName', ''),
                                    cand.get('trackName', ''),
                                    cand.get('collectionName', ''),
                                    cand.get('collectionArtistName', ''),
                                    artist, title,
                                    is_comp_type=(cand.get('collectionType') == 'Compilation'),
                                    strict_compilation_check=strict
                                )
                                scored.append((sc, cand, cat_type))
                            scored.sort(key=lambda x: x[0], reverse=True)
                            best_score, best_cand, best_cat = scored[0]
                            if best_score > 20 and best_cand.get('artworkUrl100'):
                                return {
                                    'artwork_url': best_cand['artworkUrl100'],
                                    'album': best_cand.get('collectionName', 'Unknown Album'),
                                    'artist': best_cand.get('artistName', ''),
                                    'score': best_score,
                                    'cat_type': best_cat,
                                    'provider': 'iTunes'
                                }
                except Exception:
                    time.sleep(0.1)

    return None

# --- PROVIDER 2: Deezer API ---
def search_deezer_provider(artist, title, strict=True):
    clean_t = clean_title_for_search(title)
    primary_art = get_primary_artist(artist)

    queries = [
        f"{artist} {clean_t}".strip(),
        f"{primary_art} {clean_t}".strip(),
        clean_t or title
    ]

    for q in queries:
        if not q:
            continue
        try:
            res = requests.get("https://api.deezer.com/search", params={"q": q, "limit": 15}, headers=get_random_agent_headers(), timeout=6)
            if res.status_code == 200:
                data = res.json().get('data', [])
                if data:
                    scored = []
                    for cand in data:
                        alb = cand.get('album', {})
                        art = cand.get('artist', {})
                        sc, cat_type = score_candidate(
                            art.get('name', ''),
                            cand.get('title', ''),
                            alb.get('title', ''),
                            '',
                            artist, title,
                            strict_compilation_check=strict
                        )
                        scored.append((sc, cand, cat_type))
                    scored.sort(key=lambda x: x[0], reverse=True)
                    best_score, best_cand, best_cat = scored[0]
                    alb = best_cand.get('album', {})
                    cover_url = alb.get('cover_xl') or alb.get('cover_big')
                    if best_score > 20 and cover_url:
                        return {
                            'artwork_url': cover_url,
                            'album': alb.get('title', 'Unknown Album'),
                            'artist': best_cand.get('artist', {}).get('name', ''),
                            'score': best_score,
                            'cat_type': best_cat,
                            'provider': 'Deezer'
                        }
        except Exception:
            pass

    return None

def fetch_high_res_artwork_bytes(artwork_url, provider):
    """Fetch binary image bytes at highest resolution from URL."""
    if not artwork_url:
        return None, "No URL"

    if provider == 'iTunes':
        target_resolutions = ["3000x3000bb", "1400x1400bb", "1000x1000bb", "600x600bb"]
        base_url = re.sub(r'/\d+x\d+bb\.', '/{res}.', artwork_url)
        if base_url == artwork_url:
            base_url = re.sub(r'/\d+x\d+\.', '/{res}.', artwork_url)

        for res in target_resolutions:
            test_url = base_url.format(res=res)
            try:
                r = requests.get(test_url, headers=get_random_agent_headers(), timeout=8)
                if r.status_code == 200 and len(r.content) > 10000:
                    return r.content, f"High-Res ({res.split('x')[0]}px)"
            except Exception:
                continue

    try:
        r = requests.get(artwork_url, headers=get_random_agent_headers(), timeout=8)
        if r.status_code == 200 and len(r.content) > 5000:
            return r.content, "HD Artwork (1000px)"
    except Exception:
        pass

    return None, "Download Failed"

def resolve_hybrid_artwork(artist, title):
    """Two-Tiered Hybrid Resolver Architecture."""
    res = search_itunes_provider(artist, title, strict=True)
    if not res:
        res = search_deezer_provider(artist, title, strict=True)

    if not res:
        res = search_itunes_provider(artist, title, strict=False)
    if not res:
        res = search_deezer_provider(artist, title, strict=False)

    if res and res.get('artwork_url'):
        cover_bytes, quality = fetch_high_res_artwork_bytes(res['artwork_url'], res['provider'])
        if cover_bytes:
            return {
                'cover_data': cover_bytes,
                'album': res['album'],
                'artist': res['artist'],
                'score': res['score'],
                'cat_type': res['cat_type'],
                'provider': res['provider'],
                'quality': f"{res['provider']} {quality}"
            }

    return None

def embed_artwork_to_file(file_path, cover_bytes):
    """Embed image binary data into MP3, M4A, or FLAC audio file."""
    f_lower = file_path.lower()
    try:
        if f_lower.endswith('.mp3'):
            try:
                audio = MP3(file_path, ID3=ID3)
            except ID3NoHeaderError:
                audio = MP3(file_path)
                audio.add_tags()
            if audio.tags is None:
                audio.add_tags()

            audio.tags.add(APIC(
                encoding=0,
                mime='image/jpeg',
                type=3,
                desc='Cover',
                data=cover_bytes
            ))
            audio.save(v2_version=3)
            return True

        elif f_lower.endswith('.m4a'):
            audio = MP4(file_path)
            audio['covr'] = [MP4Cover(cover_bytes, imageformat=MP4Cover.FORMAT_JPEG)]
            audio.save()
            return True

        elif f_lower.endswith('.flac'):
            audio = FLAC(file_path)
            pic = Picture()
            pic.data = cover_bytes
            pic.type = 3
            pic.mime = "image/jpeg"
            audio.add_picture(pic)
            audio.save()
            return True

    except Exception as e:
        console.print(f"[red]Error embedding artwork into '{os.path.basename(file_path)}': {e}[/red]")
        return False

    return False

def _process_single_file_worker(fname, folder_path, thread_slot, progress, master_task, worker_status):
    """Worker task with zero left-margin indentation and active track status."""
    file_path = os.path.join(folder_path, fname)
    meta = read_audio_tags(file_path)

    artist = meta['artist'] or "Unknown Artist"
    title = meta['title'] or os.path.splitext(fname)[0]
    track_display = f"{title} - {artist}"

    with STATUS_LOCK:
        worker_status[thread_slot] = f"[bold cyan]Thread #{thread_slot+1:02d}[/bold cyan] Fixing: [white]{track_display[:50]}[/white]"

    try:
        art_res = resolve_hybrid_artwork(artist, title)
        if art_res:
            success = embed_artwork_to_file(file_path, art_res['cover_data'])
            if success:
                cat_label = art_res['cat_type']
                res_struct = {
                    'fname': fname,
                    'track': track_display,
                    'album': art_res['album'],
                    'score': int(art_res['score']),
                    'quality': art_res['quality'],
                    'cat_type': cat_label,
                    'status': f'SUCCESS ({cat_label})',
                    'report': f"{fname} | {track_display} | Matched: {art_res['album']} | Score: {int(art_res['score'])} | Quality: {art_res['quality']} | SUCCESS ({cat_label})"
                }
            else:
                res_struct = {
                    'fname': fname,
                    'track': track_display,
                    'album': art_res['album'],
                    'score': 0,
                    'quality': '-',
                    'cat_type': art_res['cat_type'],
                    'status': 'EMBED_FAILED',
                    'report': f"{fname} | {track_display} | EMBED FAILED"
                }
        else:
            res_struct = {
                'fname': fname,
                'track': track_display,
                'album': 'No Match Found',
                'score': 0,
                'quality': '-',
                'cat_type': 'NO MATCH',
                'status': 'NO MATCH',
                'report': f"{fname} | {track_display} | NO MATCH"
            }
    finally:
        progress.advance(master_task)

    return res_struct

def process_album_art_fixer(folder_path=AUDIO_FOLDER, max_workers=10):
    """Batch process audio library using multi-threading with clean overview & fallbacks summary."""
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    audio_files = [
        f for f in os.listdir(folder_path)
        if f.lower().endswith(('.mp3', '.m4a', '.flac', '.aac'))
    ]

    if not audio_files:
        console.print(Panel(
            f"No supported audio files found in: [bold magenta]{folder_path}[/bold magenta]\n\n"
            "Place any .mp3, .m4a, or .flac files into this folder and run again.",
            title="Empty Audio Library",
            border_style="yellow"
        ))
        return

    console.print(f"\n[bold green]Found {len(audio_files)} audio file(s) | Multi-Threaded Engine ({max_workers} threads)...[/bold green]")

    report_rows = []
    results = []

    progress = Progress(
        SpinnerColumn(),
        TaskProgressColumn(),
        BarColumn(),
        TextColumn("[bold green]Overall Progress ({task.completed}/{task.total} tracks)[/bold green]"),
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
                future = executor.submit(_process_single_file_worker, fname, folder_path, thread_slot, progress, master_task, worker_status)
                future_to_file[future] = fname

            for future in as_completed(future_to_file):
                res = future.result()
                results.append(res)
                live.update(build_renderable())

    results.sort(key=lambda x: x['fname'].lower())
    for r in results:
        report_rows.append(r['report'])

    # --- CLI Terminal Overview Panel ---
    total_processed = len(results)
    count_studio = sum(1 for r in results if r['cat_type'] in ['Studio Album', 'Single'] and 'SUCCESS' in r['status'])
    count_fallback = sum(1 for r in results if 'Fallback' in r['cat_type'])
    count_no_match = sum(1 for r in results if r['status'] == 'NO MATCH')
    count_embed_failed = sum(1 for r in results if r['status'] == 'EMBED_FAILED')

    console.print()
    console.print(Panel(
        f"[bold white]Total Processed:[/bold white] {total_processed} files  |  "
        f"[bold green]Studio Albums / Singles Updated:[/bold green] {count_studio}  |  "
        f"[bold yellow]Soundtrack / Compilation Fallbacks:[/bold yellow] {count_fallback}  |  "
        f"[bold red]No Match / Errors:[/bold red] {count_no_match + count_embed_failed}",
        title="[bold cyan]Smart Album Art Fixer Overview[/bold cyan]",
        border_style="cyan"
    ))

    # --- CLI Terminal Exceptions & Fallbacks Summary Table ---
    exceptions = [r for r in results if 'Fallback' in r['cat_type'] or r['status'] in ['NO MATCH', 'EMBED_FAILED']]

    if exceptions:
        summary_table = Table(title="[bold yellow]Fallbacks & Non-Match Summary[/bold yellow]", border_style="cyan", header_style="bold magenta")
        summary_table.add_column("Audio File", style="bold white")
        summary_table.add_column("Track Info", style="green")
        summary_table.add_column("Matched Album", style="cyan")
        summary_table.add_column("Source & Quality", justify="center", style="magenta")
        summary_table.add_column("Status / Match Type", style="bold green")

        for r in exceptions:
            cat = r['cat_type']
            if 'Fallback' in cat:
                status_markup = f"[bold yellow]Updated ({cat})[/bold yellow]"
            elif r['status'] == 'EMBED_FAILED':
                status_markup = "[red]Embed Failed[/red]"
            else:
                status_markup = "[dim red]NO MATCH[/dim red]"

            summary_table.add_row(
                r['fname'],
                r['track'],
                r['album'],
                r['quality'],
                status_markup
            )

        console.print(summary_table)
    else:
        console.print("[bold green]All tracks matched official Studio Albums / Singles perfectly![/bold green]\n")

    # --- Write FULL Detailed Log to TXT File ---
    try:
        if not os.path.exists(REPORT_DIR):
            os.makedirs(REPORT_DIR)
        report_path = os.path.join(REPORT_DIR, "album_art_fixer_report.txt")

        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(report_path, "w", encoding="utf-8") as rf:
            rf.write("=== SMART MULTI-PROVIDER ALBUM ART FIXER REPORT ===\n")
            rf.write(f"Date & Time: {timestamp}\n")
            rf.write(f"Total Audio Files Processed: {len(audio_files)}\n")
            rf.write(f"Worker Threads Used: {max_workers}\n\n")
            rf.write("FILE NAME | TRACK INFO | MATCHED ALBUM | SCORE | SOURCE & QUALITY | STATUS & MATCH TYPE\n")
            rf.write("-" * 85 + "\n")
            for row in report_rows:
                rf.write(f"{row}\n")

        console.print(f"[bold green]Full report saved to:[/bold green] [underline magenta]playlist_sources/album_art_fixer_report.txt[/underline magenta]\n")
    except Exception as e:
        console.print(f"[dim yellow]Notice: Could not write report file: {e}[/dim yellow]")

def main():
    console.clear()
    console.print(Panel(
        "[bold cyan]SMART MULTI-PROVIDER ALBUM ART FIXER[/bold cyan]\n"
        "[bold green]1. Tier 1 Pass: Prefers Original Studio Albums & Singles (iTunes 3000px & Deezer 1000px HD).\n"
        "2. Tier 2 Pass (Super Fallback): Soundtracks, Movie Albums & Compilations if no studio album exists.\n"
        "3. High-Level Summary Overview (Full details saved to album_art_fixer_report.txt).[/bold green]",
        border_style="cyan"
    ))

    try:
        workers_input = Prompt.ask("\nSelect worker thread count (e.g. 5 to 20)", default="10")
        workers_val = int(workers_input)
    except Exception:
        workers_val = 10

    process_album_art_fixer(AUDIO_FOLDER, max_workers=workers_val)

if __name__ == '__main__':
    main()
