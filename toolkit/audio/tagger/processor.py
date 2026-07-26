"""Audio folder tagging processor and CLI."""
from __future__ import annotations

import datetime
import os
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table

from toolkit.audio.metadata import read_all_existing_metadata
from toolkit.audio.tagger.bpm import detect_physical_bpm
from toolkit.audio.tagger.metadata_fetch import get_spotify_client, search_spotify_metadata
from toolkit.audio.tagger.mood import calculate_mood
from toolkit.audio.tagger.writer import tag_m4a_file, tag_mp3_file
from toolkit.core import AUDIO_LIBRARY_DIR, REPORTS_DIR
from toolkit.core.constants import DEFAULT_MAX_WORKERS
from toolkit.core.logging import get_logger
from toolkit.playlists.parser import pre_sanitize_song_line

warnings.filterwarnings("ignore")

console = Console()
STATUS_LOCK = Lock()
logger = get_logger(__name__)


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
