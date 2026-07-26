"""
Synced Lyrics Downloader Module (.lrc).
Fetches timestamped scrolling lyrics using LrcLib & NetEase APIs for local audio files and playlist text files.
Formats clean standard headers [ti:Title], [ar:Artist], [al:Album].
Uses shared COMPILATION_KEYWORDS and pre_sanitize_song_line for DRY compliance.
"""

from __future__ import annotations

import datetime
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table

from toolkit.audio.metadata import read_local_audio_metadata
from toolkit.core import (
    AUDIO_LIBRARY_DIR,
    EXPORT_LYRICS_DIR,
    PLAYLIST_SOURCES_DIR,
    REPORTS_DIR,
    SOURCE_TEXT_FILES_DIR,
    http_get,
)
from toolkit.core.constants import DEFAULT_MAX_WORKERS, TIMEOUT_API_LONG
from toolkit.core.logging import get_logger
from toolkit.playlists.parser import COMPILATION_KEYWORDS, pre_sanitize_song_line

console = Console()
STATUS_LOCK = Lock()
logger = get_logger(__name__)

LRCLIB_GET_URL = "https://lrclib.net/api/get"
LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"


def ensure_folders() -> None:
    """Ensure destination directories exist."""
    for folder in [AUDIO_LIBRARY_DIR, PLAYLIST_SOURCES_DIR, SOURCE_TEXT_FILES_DIR, REPORTS_DIR, EXPORT_LYRICS_DIR]:
        if not os.path.exists(folder):
            os.makedirs(folder)


def filter_best_lrc_item(results: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Prioritizes official studio albums over compilations in lyric search results."""
    if not results:
        return None

    synced_studio: list[dict[str, Any]] = []
    synced_others: list[dict[str, Any]] = []
    plain_studio: list[dict[str, Any]] = []
    plain_others: list[dict[str, Any]] = []

    for item in results:
        alb_name = item.get("albumName", "").lower()
        art_name = item.get("artistName", "").lower()
        has_synced = bool(item.get("syncedLyrics"))

        is_compilation = any(k in alb_name for k in COMPILATION_KEYWORDS) or "various" in art_name

        if has_synced:
            if not is_compilation:
                synced_studio.append(item)
            else:
                synced_others.append(item)
        else:
            if not is_compilation:
                plain_studio.append(item)
            else:
                plain_others.append(item)

    if synced_studio:
        return synced_studio[0]
    if synced_others:
        return synced_others[0]
    if plain_studio:
        return plain_studio[0]
    if plain_others:
        return plain_others[0]
    return results[0]


def format_lrc_with_headers(raw_lyrics, title, artist="", album=""):
    """
    Ensures standard LRC header tags [ti:Title], [ar:Artist], [al:Album] are present
    with no blank lines before the first lyric line.
    """
    if not raw_lyrics:
        return ""

    clean_raw = raw_lyrics.lstrip()
    headers = []
    if title and not clean_raw.startswith("[ti:"):
        headers.append(f"[ti:{title}]")
    if artist and "[ar:" not in clean_raw[:200]:
        headers.append(f"[ar:{artist}]")
    if album and "[al:" not in clean_raw[:200]:
        headers.append(f"[al:{album}]")

    if headers:
        header_block = "\n".join(headers) + "\n"
        return header_block + clean_raw
    return clean_raw


def fetch_synced_lrc(track_name, artist_name="", fallback_album=""):
    """Fetch synchronized .lrc lyrics."""
    headers = {"User-Agent": "SpotifyLRCManager/1.0"}

    if artist_name:
        params = {"track_name": track_name, "artist_name": artist_name}
        try:
            r = http_get(LRCLIB_GET_URL, params=params, headers=headers, timeout=TIMEOUT_API_LONG)
            if r.status_code == 200:
                data = r.json()
                t_name = data.get("trackName") or track_name
                a_name = data.get("artistName") or artist_name
                alb_name = data.get("albumName") or fallback_album

                alb_lower = alb_name.lower()
                if any(k in alb_lower for k in COMPILATION_KEYWORDS) and fallback_album:
                    alb_name = fallback_album

                raw_lrc = data.get("syncedLyrics") or data.get("plainLyrics")
                if raw_lrc:
                    lrc_type = "Synced Lyrics (.lrc)" if data.get("syncedLyrics") else "Plain Lyrics"
                    formatted_lrc = format_lrc_with_headers(raw_lrc, t_name, a_name, alb_name)
                    return formatted_lrc, lrc_type, alb_name
        except (OSError, ValueError, KeyError) as e:
            logger.debug(f"LrcLib get failed for '{track_name}': {e}")

    query = f"{track_name} {artist_name}".strip()
    try:
        r_search = http_get(LRCLIB_SEARCH_URL, params={"q": query}, headers=headers, timeout=TIMEOUT_API_LONG)
        if r_search.status_code == 200:
            results = r_search.json()
            if results:
                target_item = filter_best_lrc_item(results)
                if not target_item:
                    return None, "Lyrics Not Found", fallback_album

                raw_lrc = target_item.get("syncedLyrics") or target_item.get("plainLyrics")
                if raw_lrc:
                    t_name = target_item.get("trackName") or track_name
                    a_name = target_item.get("artistName") or artist_name
                    alb_name = target_item.get("albumName") or fallback_album

                    alb_lower = alb_name.lower()
                    if any(k in alb_lower for k in COMPILATION_KEYWORDS) and fallback_album:
                        alb_name = fallback_album

                    lrc_type = "Synced Lyrics (.lrc)" if target_item.get("syncedLyrics") else "Plain Lyrics"
                    formatted_lrc = format_lrc_with_headers(raw_lrc, t_name, a_name, alb_name)
                    return formatted_lrc, lrc_type, alb_name
    except (OSError, ValueError, KeyError, TypeError) as e:
        logger.debug(f"LrcLib search failed for '{query}': {e}")

    return None, "Lyrics Not Found", fallback_album


def save_lrc_file(output_path, lyrics_content):
    """Save .lrc content to file."""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(lyrics_content)
        return True
    except OSError as e:
        logger.warning(f"Error saving {output_path}: {e}")
        console.print(f"[red]Error saving {output_path}: {e}[/red]")
        return False


def _process_single_lrc_worker(fname, thread_slot, progress, master_task, worker_status):
    """Worker function for fetching lyrics concurrently for single file."""
    file_path = os.path.join(AUDIO_LIBRARY_DIR, fname)
    file_base = os.path.splitext(fname)[0]
    lrc_path = os.path.join(AUDIO_LIBRARY_DIR, f"{file_base}.lrc")

    id3_title, id3_artist, id3_album = read_local_audio_metadata(file_path)

    if id3_title and id3_artist:
        query_title = id3_title
        query_artist = id3_artist
        source_label = "Audio File Tags"
    else:
        query_title = file_base
        query_artist = ""
        if ' - ' in file_base:
            parts = file_base.split(' - ', 1)
            query_artist, query_title = parts[0].strip(), parts[1].strip()
        source_label = "File Name"

    query_title = pre_sanitize_song_line(query_title)
    disp_text = f"{query_artist} - {query_title}".strip(" -")

    with STATUS_LOCK:
        worker_status[thread_slot] = (
            f"[bold cyan]Thread #{thread_slot + 1:02d}[/bold cyan] "
            f"Fetching LRC: [white]{disp_text[:50]}[/white]"
        )

    try:
        lyrics, lyric_type, album_name = fetch_synced_lrc(query_title, query_artist, id3_album or "")

        if lyrics:
            save_lrc_file(lrc_path, lyrics)
            return {
                'fname': fname,
                'source': source_label,
                'lyric_type': lyric_type,
                'success': True,
                'report': f"{fname} | {source_label} | {lyric_type}"
            }
        else:
            return {
                'fname': fname,
                'source': source_label,
                'lyric_type': 'Lyrics Not Found',
                'success': False,
                'report': f"{fname} | {source_label} | Lyrics Not Found"
            }
    finally:
        with STATUS_LOCK:
            progress.advance(master_task)


def sync_audio_library_lyrics(max_workers=DEFAULT_MAX_WORKERS):
    """Multi-threaded download of .lrc files for audio_library folder."""
    ensure_folders()
    audio_files = [f for f in os.listdir(AUDIO_LIBRARY_DIR) if f.lower().endswith(('.mp3', '.m4a', '.flac', '.aac'))]
    if not audio_files:
        console.print(f"[bold yellow]No audio files found in '{AUDIO_LIBRARY_DIR}/'.[/bold yellow]")
        return

    console.print(
        f"\n[bold green]Syncing Synced Lyrics for {
            len(audio_files)} audio file(s) | Multi-Threaded Engine ({max_workers} threads)...[/bold green]\n")

    results = []
    progress = Progress(
        SpinnerColumn(),
        TaskProgressColumn(),
        BarColumn(),
        TextColumn("[bold green]Lyrics Progress ({task.completed}/{task.total} files)[/bold green]"),
        console=console
    )
    master_task = progress.add_task("Overall", total=len(audio_files))

    worker_status = [f"[dim]Thread #{i + 1:02d}: Active...[/dim]" for i in range(max_workers)]

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
                future = executor.submit(
                    _process_single_lrc_worker,
                    fname,
                    thread_slot,
                    progress,
                    master_task,
                    worker_status)
                future_to_file[future] = fname

            for future in as_completed(future_to_file):
                res = future.result()
                results.append(res)
                live.update(build_renderable())

    results.sort(key=lambda x: x['fname'].lower())

    count_synced = sum(1 for r in results if r['success'])
    count_missing = len(results) - count_synced

    console.print()
    console.print(Panel(
        f"[bold white]Total Audio Files:[/bold white] {len(results)}  |  "
        f"[bold green]Synced Lyrics (.LRC) Saved:[/bold green] {count_synced}  |  "
        f"[bold red]Lyrics Not Found:[/bold red] {count_missing}",
        title="[bold cyan]Multi-Threaded Lyrics Downloader Overview[/bold cyan]",
        border_style="cyan"
    ))

    exceptions = [r for r in results if not r['success']]
    if exceptions:
        summary_table = Table(title="[bold yellow]Missing Lyrics Summary[/bold yellow]",
                              border_style="cyan", header_style="bold magenta")
        summary_table.add_column("Audio File", style="bold white")
        summary_table.add_column("Search Source", style="dim")
        summary_table.add_column("Status", style="red")
        for r in exceptions:
            summary_table.add_row(r['fname'], r['source'], "[dim red]Lyrics Not Found[/dim red]")
        console.print(summary_table)

    try:
        report_path = os.path.join(REPORTS_DIR, "lyrics_download_report.txt")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(report_path, "w", encoding="utf-8") as rf:
            rf.write("=== MULTI-THREADED LYRICS DOWNLOAD REPORT ===\n")
            rf.write(f"Date & Time: {timestamp}\n")
            rf.write(f"Total Audio Files: {len(audio_files)}\n")
            rf.write(f"Worker Threads Used: {max_workers}\n\n")
            rf.write("FILE NAME | SEARCH SOURCE | STATUS\n")
            rf.write("-" * 60 + "\n")
            for r in results:
                rf.write(f"{r['report']}\n")
        console.print(
            "\n[bold green]Report saved to:[/bold green] "
            "[underline magenta]reports/lyrics_download_report.txt[/underline magenta]\n"
        )
    except OSError as e:
        logger.warning(f"Could not write report file: {e}")
        console.print(f"[dim yellow]Notice: Could not write report file: {e}[/dim yellow]")


def sync_playlist_text_lyrics():
    """Download .lrc files for songs listed in a playlist text file."""
    ensure_folders()

    txt_candidates = []
    seen_names = set()

    # Priority 1: source_text_files
    if os.path.exists(SOURCE_TEXT_FILES_DIR):
        for f in sorted(os.listdir(SOURCE_TEXT_FILES_DIR)):
            if f.lower().endswith('.txt') and not f.lower().endswith('_report.txt'):
                txt_candidates.append(os.path.join(SOURCE_TEXT_FILES_DIR, f))
                seen_names.add(f)

    # Priority 2: playlist_sources fallback
    if os.path.exists(PLAYLIST_SOURCES_DIR):
        for f in sorted(os.listdir(PLAYLIST_SOURCES_DIR)):
            if f.lower().endswith('.txt') and not f.lower().endswith('_report.txt') and f not in seen_names:
                fpath = os.path.join(PLAYLIST_SOURCES_DIR, f)
                if os.path.isfile(fpath):
                    txt_candidates.append(fpath)

    if not txt_candidates:
        console.print(f"[bold yellow]No text files found in '{SOURCE_TEXT_FILES_DIR}/'.[/bold yellow]")
        return

    console.print("\n[bold yellow]Select a Playlist Text file to download lyrics for:[/bold yellow]")
    for idx, fpath in enumerate(txt_candidates, 1):
        fname = os.path.basename(fpath)
        console.print(f" [bold cyan]{idx}[/bold cyan] {fname}")

    valid_indices = [str(i) for i in range(1, len(txt_candidates) + 1)]
    choice = Prompt.ask("\nSelect file index", choices=valid_indices)
    txt_path = txt_candidates[int(choice) - 1]
    selected_txt = os.path.basename(txt_path)

    songs = []
    with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            c = line.strip()
            if c and not c.startswith("==="):
                songs.append(c)

    if not songs:
        console.print(f"[bold red]No song entries in {selected_txt}.[/bold red]")
        return

    console.print(f"\n[bold green]Fetching lyrics for {len(songs)} song(s) from '{selected_txt}'[/bold green]\n")

    summary_table = Table(title=f"Synced Lyrics for {selected_txt}", border_style="cyan", header_style="bold magenta")
    summary_table.add_column("Song Name", style="bold white")
    summary_table.add_column("Status", style="green")
    summary_table.add_column("Saved Location", style="dim")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Fetching lyrics...", total=len(songs))

        for song_line in songs:
            clean_line = pre_sanitize_song_line(song_line)
            query_title = clean_line
            query_artist = ""
            if ' - ' in clean_line:
                parts = clean_line.split(' - ', 1)
                query_title, query_artist = parts[0].strip(), parts[1].strip()

            clean_filename = "".join([c for c in clean_line if c.isalnum() or c in (' ', '-', '_')]).strip()
            lrc_filename = f"{clean_filename}.lrc"
            lrc_path = os.path.join(EXPORT_LYRICS_DIR, lrc_filename)

            progress.update(task, description=f"Fetching: [dim]{clean_line[:25]}...[/dim]")

            lyrics, lyric_type, album_name = fetch_synced_lrc(query_title, query_artist)

            if lyrics:
                save_lrc_file(lrc_path, lyrics)
                summary_table.add_row(clean_line,
                                      f"[bold green]{lyric_type}[/bold green]",
                                      f"playlist_exports/lyrics/{lrc_filename}")
            else:
                summary_table.add_row(clean_line, "[dim red]Not Found[/dim red]", "-")

            progress.advance(task)

    console.print(summary_table)


def search_single_lrc():
    """Search and download .lrc for a single track."""
    ensure_folders()
    console.print("\n[bold cyan]Search Lyrics for a Single Track:[/bold cyan]")
    song_input = Prompt.ask("Enter Song Title and Artist (e.g. Nina - .Feast)")
    if not song_input.strip():
        return

    clean_input = pre_sanitize_song_line(song_input)
    query_title = clean_input
    query_artist = ""
    if ' - ' in clean_input:
        parts = clean_input.split(' - ', 1)
        query_title, query_artist = parts[0].strip(), parts[1].strip()

    lyrics, lyric_type, album_name = fetch_synced_lrc(query_title, query_artist)
    if lyrics:
        clean_filename = "".join([c for c in clean_input if c.isalnum() or c in (' ', '-', '_')]).strip()
        lrc_path = os.path.join(EXPORT_LYRICS_DIR, f"{clean_filename}.lrc")
        save_lrc_file(lrc_path, lyrics)

        console.print(Panel(
            "\n".join(lyrics.splitlines()[:12]) + "\n...",
            title=f"Saved {lyric_type} to playlist_exports/lyrics/{clean_filename}.lrc",
            border_style="green"
        ))
    else:
        console.print(f"[bold red]Could not find lyrics for '{song_input}'[/bold red]")


def main():
    ensure_folders()
    while True:
        console.clear()
        console.print(Panel(
            "[bold cyan]SYNCED LYRICS DOWNLOADER (.LRC)[/bold cyan]\n"
            "[dim]Downloads scrolling timestamped lyrics for audio files and text lists via Multi-Threading[/dim]",
            border_style="green"
        ))

        console.print("\n[bold yellow]LYRICS MENU OPTIONS:[/bold yellow]")
        console.print(" [bold cyan]1[/bold cyan] Sync Lyrics for Local Audio Files (audio_library/) [Multi-Threaded]")
        console.print(" [bold cyan]2[/bold cyan] Download Lyrics for Playlist Text Files (playlist_sources/)")
        console.print(" [bold cyan]3[/bold cyan] Search & Download Lyrics for a Single Track")
        console.print(" [bold cyan]0[/bold cyan] Return to Main Menu")

        choice = Prompt.ask("\nSelect option", choices=["1", "2", "3", "0"], default="1")

        if choice == "1":
            try:
                workers_input = Prompt.ask(
                    "\nSelect worker thread count (e.g. 5 to 20)",
                    default=str(DEFAULT_MAX_WORKERS),
                )
                workers_val = int(workers_input)
            except (ValueError, TypeError):
                workers_val = DEFAULT_MAX_WORKERS
            sync_audio_library_lyrics(max_workers=workers_val)
            Prompt.ask("\nPress Enter to return")
        elif choice == "2":
            sync_playlist_text_lyrics()
            Prompt.ask("\nPress Enter to return")
        elif choice == "3":
            search_single_lrc()
            Prompt.ask("\nPress Enter to return")
        elif choice == "0":
            break


if __name__ == '__main__':
    main()
