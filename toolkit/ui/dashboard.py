"""
Master UI Dashboard & Interactive Menu.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional

import spotipy
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from spotipy.oauth2 import SpotifyClientCredentials

from toolkit.audio import sync_audio_library_lyrics, tag_audio_folder
from toolkit.core import (
    AUDIO_LIBRARY_DIR,
    SPOTIPY_CLIENT_ID,
    SPOTIPY_CLIENT_SECRET,
    ensure_all_folders,
    get_all_txt_files,
    get_network_session,
)
from toolkit.core.logging import get_logger, setup_logging
from toolkit.playlists import run_apple_music_playlist_creator, run_spotify_playlist_creator

console = Console()
logger = get_logger(__name__)


def check_spotify_connection() -> tuple[Optional[Any], str]:
    """Check Spotify API connection status seamlessly without blocking."""
    if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET:
        return None, "[bold red]Offline (Missing .env API Keys)[/bold red]"
    try:
        session = get_network_session()
        auth_mgr = SpotifyClientCredentials(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
            requests_session=session,
        )
        sp = spotipy.Spotify(client_credentials_manager=auth_mgr, requests_session=session)
        sp.search(q="test", limit=1, type="track")
        return sp, "[bold green]API Connection Active (Ready)[/bold green]"
    except (spotipy.SpotifyException, OSError, ValueError) as e:
        logger.debug(f"Spotify connection check failed: {e}")
        return None, "[bold yellow]Offline (Invalid API Credentials)[/bold yellow]"


def display_dashboard():
    """Display main dashboard header."""
    console.clear()
    sp_client, sp_status = check_spotify_connection()

    txt_files = get_all_txt_files()
    if os.path.exists(AUDIO_LIBRARY_DIR):
        audio_files = [
            f for f in os.listdir(AUDIO_LIBRARY_DIR) if f.endswith((".mp3", ".m4a", ".flac", ".aac"))
        ]
    else:
        audio_files = []

    header_text = (
        "[bold cyan]SPOTIFY - APPLE MUSIC TOOLKIT[/bold cyan]\n"
        "Unified Master Dashboard for Playlists, Audio Tagging & Synced Lyrics\n\n"
        f"- {sp_status}\n"
        f"- [bold white]Text Playlist Files:[/bold white] "
        f"[bold magenta]{len(txt_files)} file(s)[/bold magenta] "
        "in [dim]playlist_sources/source_text_files/[/dim]\n"
        f"- [bold white]Local Audio Tracks:[/bold white] "
        f"[bold magenta]{len(audio_files)} track(s)[/bold magenta] "
        "in [dim]audio_library/[/dim]"
    )

    console.print(Panel(header_text, border_style="green"))


def run_one_click_complete_process():
    """
    1-Click Master Batch Action:
    Step 1: Tag Audio Metadata (Title, Artist, Album, Genre, Tempo/BPM, Music Style/Mood, Album Art)
    Step 2: Download Synced .LRC Lyrics
    """
    console.clear()
    console.print(Panel(
        "[bold cyan]COMPLETE AUDIO LIBRARY PROCESSING (1-CLICK BATCH)[/bold cyan]\n"
        "[dim]Automatically performs:\n"
        "1. Song Metadata Tagging & Tempo (BPM) Calculation\n"
        "2. Music Style / Mood Tagging\n"
        "3. High-Resolution Album Artwork Embedding\n"
        "4. Synchronized Lyrics (.LRC) Downloading[/dim]",
        border_style="magenta"
    ))

    console.print("\n[bold green]Step 1: Tagging Audio Files & Calculating Tempo (BPM)...[/bold green]")
    tag_audio_folder(AUDIO_LIBRARY_DIR, mode="1")

    console.print("\n[bold green]Step 2: Downloading Synced Lyrics (.LRC)...[/bold green]")
    sync_audio_library_lyrics()

    console.print(
        Panel(
            "[bold green]Complete Audio Library Processing Finished Successfully![/bold green]",
            border_style="green"))


def scan_workspace_overview():
    """Display detailed overview of playlist sources and audio library files."""
    console.clear()
    console.print(Panel("[bold cyan]WORKSPACE OVERVIEW & FILE STATUS[/bold cyan]", border_style="blue"))

    txt_files = get_all_txt_files()
    t1 = Table(title="Playlist Text Files (playlist_sources/source_text_files/)",
               border_style="magenta", header_style="bold cyan")
    t1.add_column("Index", style="bold yellow", justify="center")
    t1.add_column("File Name", style="bold white")
    t1.add_column("Folder Location", style="dim white")
    t1.add_column("Song Count", justify="right", style="green")

    for idx, item in enumerate(txt_files, 1):
        count = 0
        with open(item['path'], 'r', encoding='utf-8', errors='ignore') as f:
            for raw_line in f:
                c = raw_line.strip()
                if c and not c.startswith("==="):
                    count += 1
        t1.add_row(str(idx), item['name'], item['rel'], str(count))

    console.print(t1)

    audio_files = [f for f in os.listdir(AUDIO_LIBRARY_DIR) if f.endswith(
        ('.mp3', '.m4a', '.flac', '.aac'))] if os.path.exists(AUDIO_LIBRARY_DIR) else []
    t2 = Table(title="Audio Library Tracks (audio_library/)", border_style="green", header_style="bold magenta")
    t2.add_column("Index", style="bold yellow", justify="center")
    t2.add_column("Audio File Name", style="bold white")
    t2.add_column("Synced Lyrics (.LRC)", justify="center", style="cyan")

    for idx, fname in enumerate(audio_files, 1):
        base_name = os.path.splitext(fname)[0]
        has_lrc = os.path.exists(os.path.join(AUDIO_LIBRARY_DIR, f"{base_name}.lrc"))
        lrc_status = "[bold green]Present (.lrc)[/bold green]" if has_lrc else "[dim red]Missing (.lrc)[/dim red]"
        t2.add_row(str(idx), fname, lrc_status)

    console.print(t2)


def main() -> None:
    setup_logging()
    ensure_all_folders()

    while True:
        display_dashboard()

        console.print("\n[bold yellow]MAIN MENU OPTIONS:[/bold yellow]")
        console.print(
            " [bold bright_white]1[/bold bright_white] "
            "[bold bright_yellow]Complete Process Audio Library[/bold bright_yellow] "
            "[dim](Auto-Tag Metadata + Tempo + Style + Synced Lyrics)[/dim]"
        )
        console.print(
            " [bold bright_white]2[/bold bright_white] "
            "[bold green]Spotify Playlist Creator[/bold green] "
            "[dim](Convert Text Files to Spotify Playlists)[/dim]"
        )
        console.print(
            " [bold bright_white]3[/bold bright_white] "
            "[bold bright_red]Apple Music Playlist Creator[/bold bright_red] "
            "[dim](Convert Text Files to Apple Music Playlists)[/dim]"
        )
        console.print(
            " [bold bright_white]4[/bold bright_white] "
            "[bold cyan]Audio Tagger[/bold cyan] "
            "[dim](Song Metadata, Tempo & Album Art)[/dim]"
        )
        console.print(
            " [bold bright_white]5[/bold bright_white] "
            "[bold bright_blue]Synced Lyrics Downloader[/bold bright_blue] "
            "[dim](.LRC Lyrics Only)[/dim]"
        )
        console.print(
            " [bold bright_white]6[/bold bright_white] "
            "[bold magenta]Album Art Fixer[/bold magenta] "
            "[dim](Fix & Replace Artwork via iTunes API with Scoring)[/dim]"
        )
        console.print(
            " [bold bright_white]7[/bold bright_white] "
            "[bold yellow]View Workspace Files & Status[/bold yellow]"
        )
        console.print(" [bold bright_white]0[/bold bright_white] [dim white]Exit[/dim white]")

        choice = Prompt.ask("\nSelect option", choices=["1", "2", "3", "4", "5", "6", "7", "0"], default="1")

        if choice == "1":
            run_one_click_complete_process()
            Prompt.ask("\nPress Enter to return")

        elif choice == "2":
            run_spotify_playlist_creator()
            Prompt.ask("\nPress Enter to return")

        elif choice == "3":
            run_apple_music_playlist_creator()
            Prompt.ask("\nPress Enter to return")

        elif choice == "4":
            import toolkit.audio.tagger as tagger
            tagger.main()
            Prompt.ask("\nPress Enter to return")

        elif choice == "5":
            import toolkit.audio.lyrics as lyrics
            lyrics.main()
            Prompt.ask("\nPress Enter to return")

        elif choice == "6":
            import toolkit.audio.artwork as artwork
            artwork.main()
            Prompt.ask("\nPress Enter to return")

        elif choice == "7":
            scan_workspace_overview()
            Prompt.ask("\nPress Enter to return")

        elif choice == "0":
            console.print("\n[bold cyan]Thank you for using Spotify - Apple Music Toolkit. Goodbye![/bold cyan]")
            sys.exit(0)


if __name__ == "__main__":
    main()
