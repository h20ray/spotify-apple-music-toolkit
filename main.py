import os
import sys
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
console = Console()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYLIST_SOURCES_DIR = os.path.join(BASE_DIR, "playlist_sources")
AUDIO_LIBRARY_DIR = os.path.join(BASE_DIR, "audio_library")

CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')

def ensure_all_folders():
    """Ensure all required project directories exist."""
    for folder in [PLAYLIST_SOURCES_DIR, AUDIO_LIBRARY_DIR, os.path.join(PLAYLIST_SOURCES_DIR, "lyrics")]:
        if not os.path.exists(folder):
            os.makedirs(folder)

def check_spotify_connection():
    """Check Spotify API connection status seamlessly without blocking."""
    if not CLIENT_ID or not CLIENT_SECRET:
        return None, "[bold red]Offline (Missing .env API Keys)[/bold red]"
    try:
        auth_mgr = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
        sp = spotipy.Spotify(client_credentials_manager=auth_mgr)
        sp.search(q="test", limit=1, type="track")
        return sp, "[bold green]API Connection Active (Ready)[/bold green]"
    except Exception:
        return None, "[bold yellow]Offline (Invalid API Credentials)[/bold yellow]"

def display_dashboard():
    """Display main dashboard header."""
    console.clear()
    sp_client, sp_status = check_spotify_connection()

    txt_files = [f for f in os.listdir(PLAYLIST_SOURCES_DIR) if f.endswith('.txt')] if os.path.exists(PLAYLIST_SOURCES_DIR) else []
    audio_files = [f for f in os.listdir(AUDIO_LIBRARY_DIR) if f.endswith(('.mp3', '.m4a', '.flac', '.aac'))] if os.path.exists(AUDIO_LIBRARY_DIR) else []

    header_text = f"""[bold cyan]SPOTIFY & AUDIO MUSIC TOOLKIT[/bold cyan]
Unified Master Dashboard for Playlists, Audio Tagging & Synced Lyrics

- {sp_status}
- [bold white]Text Playlist Files:[/bold white] [bold magenta]{len(txt_files)} file(s)[/bold magenta] in [dim]playlist_sources/[/dim]
- [bold white]Local Audio Tracks:[/bold white] [bold magenta]{len(audio_files)} track(s)[/bold magenta] in [dim]audio_library/[/dim]"""

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
    import audio_tagger
    audio_tagger.process_audio_folder(AUDIO_LIBRARY_DIR, mode="1")

    console.print("\n[bold green]Step 2: Downloading Synced Lyrics (.LRC)...[/bold green]")
    import lyrics_downloader
    lyrics_downloader.sync_audio_library_lyrics()

    console.print(Panel("[bold green]Complete Audio Library Processing Finished Successfully![/bold green]", border_style="green"))

def scan_workspace_overview():
    """Display detailed overview of playlist sources and audio library files."""
    console.clear()
    console.print(Panel("[bold cyan]WORKSPACE OVERVIEW & FILE STATUS[/bold cyan]", border_style="blue"))

    txt_files = [f for f in os.listdir(PLAYLIST_SOURCES_DIR) if f.endswith('.txt')] if os.path.exists(PLAYLIST_SOURCES_DIR) else []
    t1 = Table(title="Playlist Text Files (playlist_sources/)", border_style="magenta", header_style="bold cyan")
    t1.add_column("Index", style="bold yellow", justify="center")
    t1.add_column("File Name", style="bold white")
    t1.add_column("Song Count", justify="right", style="green")
    
    for idx, fname in enumerate(txt_files, 1):
        fpath = os.path.join(PLAYLIST_SOURCES_DIR, fname)
        count = 0
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            for l in f:
                c = l.strip()
                if c and not c.startswith("==="):
                    count += 1
        t1.add_row(str(idx), fname, str(count))

    console.print(t1)

    audio_files = [f for f in os.listdir(AUDIO_LIBRARY_DIR) if f.endswith(('.mp3', '.m4a', '.flac', '.aac'))] if os.path.exists(AUDIO_LIBRARY_DIR) else []
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

def main():
    ensure_all_folders()

    while True:
        display_dashboard()

        console.print("\n[bold yellow]MAIN MENU OPTIONS:[/bold yellow]")
        console.print(" [bold cyan]1[/bold cyan] [bold green]Complete Process Audio Library[/bold green] (Auto-Tag Metadata + Tempo + Style + Synced Lyrics)")
        console.print(" [bold cyan]2[/bold cyan] Spotify Playlist Creator (Convert Text Files to Spotify Playlists)")
        console.print(" [bold cyan]3[/bold cyan] Audio Tagger (Song Metadata, Tempo & Album Art)")
        console.print(" [bold cyan]4[/bold cyan] Synced Lyrics Downloader (.LRC Lyrics Only)")
        console.print(" [bold cyan]5[/bold cyan] View Workspace Files & Status")
        console.print(" [bold cyan]0[/bold cyan] Exit")

        choice = Prompt.ask("\nSelect option", choices=["1", "2", "3", "4", "5", "0"], default="1")

        if choice == "1":
            run_one_click_complete_process()
            Prompt.ask("\nPress Enter to return")

        elif choice == "2":
            import playlist_creator
            playlist_creator.main()
            Prompt.ask("\nPress Enter to return")

        elif choice == "3":
            import audio_tagger
            audio_tagger.main()
            Prompt.ask("\nPress Enter to return")

        elif choice == "4":
            import lyrics_downloader
            lyrics_downloader.main()
            Prompt.ask("\nPress Enter to return")

        elif choice == "5":
            scan_workspace_overview()
            Prompt.ask("\nPress Enter to return")

        elif choice == "0":
            console.print("\n[bold cyan]Thank you for using Spotify & Audio Toolkit. Goodbye![/bold cyan]")
            sys.exit(0)

if __name__ == '__main__':
    main()
