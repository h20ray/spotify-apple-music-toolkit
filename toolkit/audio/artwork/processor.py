"""Album art fixer processor and CLI."""
from __future__ import annotations

import datetime
import os
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table

from toolkit.audio.artwork.embed import embed_artwork
from toolkit.audio.artwork.sources import (
    fetch_artwork_bytes,
    get_high_res_artwork_deezer,
    get_high_res_artwork_itunes,
    sanitize_search_query,
)
from toolkit.audio.metadata import read_audio_tags
from toolkit.core import AUDIO_LIBRARY_DIR, REPORTS_DIR
from toolkit.core.constants import DEFAULT_MAX_WORKERS
from toolkit.core.logging import get_logger

warnings.filterwarnings("ignore")

console = Console()
STATUS_LOCK = Lock()
logger = get_logger(__name__)


def _process_single_artwork_worker(
    fname: str,
    folder_path: str,
    thread_slot: int,
    progress: Progress,
    master_task: Any,
    worker_status: list[str],
) -> dict[str, Any]:
    """Worker function for fixing artwork concurrently for a single audio file."""
    file_path = os.path.join(folder_path, fname)
    info = read_audio_tags(file_path)
    query = sanitize_search_query(info["title"], info["artist"], fname)

    with STATUS_LOCK:
        worker_status[thread_slot] = (
            f"[bold cyan]Thread #{thread_slot+1:02d}[/bold cyan] Searching Art: [white]{query[:50]}[/white]"
        )

    try:
        art_url = get_high_res_artwork_itunes(query, info["album"])
        source_label = "iTunes API (1000x1000)"

        if not art_url:
            art_url = get_high_res_artwork_deezer(query)
            source_label = "Deezer API (High-Res)"

        if not art_url:
            return {
                "fname": fname,
                "query": query,
                "source": "Not Found",
                "success": False,
                "report": f"{fname} | {query} | Not Found",
            }

        img_bytes = fetch_artwork_bytes(art_url)
        if not img_bytes:
            return {
                "fname": fname,
                "query": query,
                "source": f"{source_label} (Fetch Error)",
                "success": False,
                "report": f"{fname} | {query} | Fetch Error",
            }

        success = embed_artwork(file_path, img_bytes)
        return {
            "fname": fname,
            "query": query,
            "source": source_label,
            "success": success,
            "report": (
                f"{fname} | {query} | {source_label} | Embedded ({len(img_bytes)//1024} KB)"
                if success
                else f"{fname} | {query} | Embedding Failed"
            ),
        }
    finally:
        with STATUS_LOCK:
            progress.advance(master_task)


def process_album_art_fixer(folder_path: str = AUDIO_LIBRARY_DIR, max_workers: int = DEFAULT_MAX_WORKERS) -> None:
    """Multi-threaded scan of audio_library folder to download and embed high-res cover artwork."""
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    audio_files = [
        f for f in os.listdir(folder_path) if f.lower().endswith((".mp3", ".m4a", ".flac", ".aac"))
    ]

    if not audio_files:
        console.print(
            Panel(
                f"No audio files found in: [bold magenta]{folder_path}[/bold magenta]\n\n"
                "Place any .mp3, .m4a, or .flac files into this folder and run again.",
                title="Empty Audio Folder",
                border_style="yellow",
            )
        )
        return

    console.print(
        f"\n[bold green]Found {len(audio_files)} audio file(s) | Multi-Threaded Cover Art Fixer ({max_workers} threads)...[/bold green]"
    )

    results: list[dict[str, Any]] = []
    progress = Progress(
        SpinnerColumn(),
        TaskProgressColumn(),
        BarColumn(),
        TextColumn("[bold green]Artwork Progress ({task.completed}/{task.total} files)[/bold green]"),
        console=console,
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
                future = executor.submit(
                    _process_single_artwork_worker,
                    fname,
                    folder_path,
                    thread_slot,
                    progress,
                    master_task,
                    worker_status,
                )
                future_to_file[future] = fname

            for future in as_completed(future_to_file):
                res = future.result()
                results.append(res)
                live.update(build_renderable())

    results.sort(key=lambda x: x["fname"].lower())

    count_success = sum(1 for r in results if r["success"])
    count_failed = len(results) - count_success

    console.print()
    console.print(
        Panel(
            f"[bold white]Total Processed:[/bold white] {len(results)} files  |  "
            f"[bold green]High-Res Artwork Embedded:[/bold green] {count_success}  |  "
            f"[bold red]Failed/Not Found:[/bold red] {count_failed}",
            title="[bold cyan]Multi-Threaded Album Art Fixer Overview[/bold cyan]",
            border_style="cyan",
        )
    )

    try:
        if not os.path.exists(REPORTS_DIR):
            os.makedirs(REPORTS_DIR)
        report_path = os.path.join(REPORTS_DIR, "album_art_fixer_report.txt")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(report_path, "w", encoding="utf-8") as rf:
            rf.write("=== MULTI-THREADED ALBUM ART FIXER REPORT ===\n")
            rf.write(f"Date & Time: {timestamp}\n")
            rf.write(f"Total Processed Tracks: {len(audio_files)}\n")
            rf.write(f"Worker Threads Used: {max_workers}\n\n")
            rf.write("FILE NAME | QUERY | ARTWORK SOURCE | STATUS\n")
            rf.write("-" * 80 + "\n")
            for r in results:
                rf.write(f"{r['report']}\n")

        console.print(
            "[bold green]Full report saved to:[/bold green] "
            "[underline magenta]reports/album_art_fixer_report.txt[/underline magenta]\n"
        )
    except OSError as e:
        logger.warning(f"Could not write report file: {e}")
        console.print(f"[dim yellow]Notice: Could not write report file: {e}[/dim yellow]")


def main() -> None:
    console.clear()
    console.print(
        Panel(
            "[bold cyan]HIGH-RESOLUTION ALBUM ART FIXER (1000x1000)[/bold cyan]\n"
            "[bold green]Downloads & Embeds studio cover art into local MP3, M4A, and FLAC files.[/bold green]",
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

    process_album_art_fixer(AUDIO_LIBRARY_DIR, max_workers=workers_val)




if __name__ == "__main__":
    main()
