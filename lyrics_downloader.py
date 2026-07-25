import os
import sys
import requests
from dotenv import load_dotenv

import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from mutagen.mp4 import MP4

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
console = Console()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_FOLDER = os.path.join(BASE_DIR, "audio_library")
PLAYLIST_FOLDER = os.path.join(BASE_DIR, "playlist_sources")
LYRICS_OUTPUT_FOLDER = os.path.join(PLAYLIST_FOLDER, "lyrics")

LRCLIB_GET_URL = "https://lrclib.net/api/get"
LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"

COMPILATION_KEYWORDS = ["various artists", "compilation", "greatest hits", "best of", "now that's what i call", "top 100", "essential classics", "soundtrack"]

def ensure_folders():
    """Ensure destination directories exist."""
    for folder in [AUDIO_FOLDER, PLAYLIST_FOLDER, LYRICS_OUTPUT_FOLDER]:
        if not os.path.exists(folder):
            os.makedirs(folder)

def filter_best_lrc_item(results):
    """Prioritizes official studio albums over compilations in lyric search results."""
    if not results:
        return None
        
    synced_studio = []
    synced_others = []
    plain_studio = []
    plain_others = []

    for item in results:
        alb_name = item.get("albumName", "").lower()
        art_name = item.get("artistName", "").lower()
        has_synced = bool(item.get("syncedLyrics"))
        
        is_compilation = (
            any(k in alb_name for k in COMPILATION_KEYWORDS) or
            'various' in art_name
        )

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
    elif synced_others:
        return synced_others[0]
    elif plain_studio:
        return plain_studio[0]
    elif plain_others:
        return plain_others[0]
    return results[0]

def read_local_audio_metadata(file_path):
    """Read Title, Artist, Album directly from local MP3 or M4A file tags."""
    title, artist, album = None, None, None
    file_lower = file_path.lower()
    
    if file_lower.endswith('.mp3'):
        try:
            audio = MP3(file_path, ID3=ID3)
            if audio.tags:
                if 'TIT2' in audio.tags and audio.tags['TIT2'].text:
                    title = str(audio.tags['TIT2'].text[0]).strip()
                if 'TPE1' in audio.tags and audio.tags['TPE1'].text:
                    artist = str(audio.tags['TPE1'].text[0]).strip()
                if 'TALB' in audio.tags and audio.tags['TALB'].text:
                    album = str(audio.tags['TALB'].text[0]).strip()
        except Exception:
            pass
    elif file_lower.endswith('.m4a'):
        try:
            audio = MP4(file_path)
            if '\xa9nam' in audio and audio['\xa9nam']:
                title = str(audio['\xa9nam'][0]).strip()
            if '\xa9ART' in audio and audio['\xa9ART']:
                artist = str(audio['\xa9ART'][0]).strip()
            if '\xa9alb' in audio and audio['\xa9alb']:
                album = str(audio['\xa9alb'][0]).strip()
        except Exception:
            pass

    return title, artist, album

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
            r = requests.get(LRCLIB_GET_URL, params=params, headers=headers, timeout=10)
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
        except Exception:
            pass

    query = f"{track_name} {artist_name}".strip()
    try:
        r_search = requests.get(LRCLIB_SEARCH_URL, params={"q": query}, headers=headers, timeout=10)
        if r_search.status_code == 200:
            results = r_search.json()
            if results:
                target_item = filter_best_lrc_item(results)

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
    except Exception:
        pass

    return None, "Lyrics Not Found", fallback_album

def save_lrc_file(output_path, lyrics_content):
    """Save .lrc content to file."""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(lyrics_content)
        return True
    except Exception as e:
        console.print(f"[red]Error saving {output_path}: {e}[/red]")
        return False

def sync_audio_library_lyrics():
    """Download .lrc files for audio_library folder."""
    audio_files = [f for f in os.listdir(AUDIO_FOLDER) if f.lower().endswith(('.mp3', '.m4a', '.flac', '.aac'))]
    if not audio_files:
        console.print(f"[bold yellow]No audio files found in '{AUDIO_FOLDER}/'.[/bold yellow]")
        return

    console.print(f"\n[bold green]Syncing Synced Lyrics for {len(audio_files)} audio file(s)[/bold green]\n")

    summary_table = Table(title="Audio Library Synced Lyrics", border_style="cyan", header_style="bold magenta")
    summary_table.add_column("Audio File", style="bold white")
    summary_table.add_column("Search Source", style="dim")
    summary_table.add_column("Status", style="green")
    report_rows = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Fetching lyrics...", total=len(audio_files))

        for fname in audio_files:
            file_path = os.path.join(AUDIO_FOLDER, fname)
            file_base = os.path.splitext(fname)[0]
            lrc_path = os.path.join(AUDIO_FOLDER, f"{file_base}.lrc")
            
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

            progress.update(task, description=f"Fetching: [dim]{query_title[:25]}...[/dim]")

            lyrics, lyric_type, album_name = fetch_synced_lrc(query_title, query_artist, id3_album or "")

            if lyrics:
                save_lrc_file(lrc_path, lyrics)
                summary_table.add_row(fname, source_label, f"[bold green]{lyric_type}[/bold green]")
                report_rows.append(f"{fname} | {source_label} | {lyric_type}")
            else:
                summary_table.add_row(fname, source_label, "[dim red]Lyrics Not Found[/dim red]")
                report_rows.append(f"{fname} | {source_label} | Lyrics Not Found")

            progress.advance(task)

    console.print(summary_table)

    try:
        report_path = os.path.join(PLAYLIST_FOLDER, "lyrics_download_report.txt")
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(report_path, "w", encoding="utf-8") as rf:
            rf.write(f"=== LYRICS DOWNLOAD REPORT ===\n")
            rf.write(f"Date & Time: {timestamp}\n")
            rf.write(f"Total Audio Files: {len(audio_files)}\n\n")
            rf.write("FILE NAME | SEARCH SOURCE | STATUS\n")
            rf.write("-" * 60 + "\n")
            for row in report_rows:
                rf.write(f"{row}\n")
        console.print(f"\n[bold green]Report saved to:[/bold green] [underline magenta]playlist_sources/lyrics_download_report.txt[/underline magenta]")
    except Exception as e:
        console.print(f"[dim yellow]Notice: Could not write report file: {e}[/dim yellow]")

def sync_playlist_text_lyrics():
    """Download .lrc files for songs listed in a playlist text file."""
    txt_files = [f for f in os.listdir(PLAYLIST_FOLDER) if f.lower().endswith('.txt')]
    if not txt_files:
        console.print(f"[bold yellow]No text files found in '{PLAYLIST_FOLDER}/'.[/bold yellow]")
        return

    console.print("\n[bold yellow]Select a Playlist Text file to download lyrics for:[/bold yellow]")
    for idx, fname in enumerate(txt_files, 1):
        console.print(f" [bold cyan]{idx}[/bold cyan] {fname}")

    valid_indices = [str(i) for i in range(1, len(txt_files) + 1)]
    choice = Prompt.ask("\nSelect file index", choices=valid_indices)
    selected_txt = txt_files[int(choice) - 1]
    txt_path = os.path.join(PLAYLIST_FOLDER, selected_txt)

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
            query_title = song_line
            query_artist = ""
            if ' - ' in song_line:
                parts = song_line.split(' - ', 1)
                query_title, query_artist = parts[0].strip(), parts[1].strip()

            clean_filename = "".join([c for c in song_line if c.isalnum() or c in (' ', '-', '_')]).strip()
            lrc_filename = f"{clean_filename}.lrc"
            lrc_path = os.path.join(LYRICS_OUTPUT_FOLDER, lrc_filename)

            progress.update(task, description=f"Fetching: [dim]{song_line[:25]}...[/dim]")

            lyrics, lyric_type, album_name = fetch_synced_lrc(query_title, query_artist)

            if lyrics:
                save_lrc_file(lrc_path, lyrics)
                summary_table.add_row(song_line, f"[bold green]{lyric_type}[/bold green]", f"playlist_sources/lyrics/{lrc_filename}")
            else:
                summary_table.add_row(song_line, "[dim red]Not Found[/dim red]", "-")

            progress.advance(task)

    console.print(summary_table)

def search_single_lrc():
    """Search and download .lrc for a single track."""
    console.print("\n[bold cyan]Search Lyrics for a Single Track:[/bold cyan]")
    song_input = Prompt.ask("Enter Song Title and Artist (e.g. Nina - .Feast)")
    if not song_input.strip():
        return

    query_title = song_input
    query_artist = ""
    if ' - ' in song_input:
        parts = song_input.split(' - ', 1)
        query_title, query_artist = parts[0].strip(), parts[1].strip()

    lyrics, lyric_type, album_name = fetch_synced_lrc(query_title, query_artist)
    if lyrics:
        clean_filename = "".join([c for c in song_input if c.isalnum() or c in (' ', '-', '_')]).strip()
        lrc_path = os.path.join(LYRICS_OUTPUT_FOLDER, f"{clean_filename}.lrc")
        save_lrc_file(lrc_path, lyrics)

        console.print(Panel(
            "\n".join(lyrics.splitlines()[:12]) + "\n...",
            title=f"Saved {lyric_type} to playlist_sources/lyrics/{clean_filename}.lrc",
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
            "[dim]Downloads scrolling timestamped lyrics for audio files and text lists[/dim]",
            border_style="green"
        ))

        console.print("\n[bold yellow]LYRICS MENU OPTIONS:[/bold yellow]")
        console.print(" [bold cyan]1[/bold cyan] Sync Lyrics for Local Audio Files (audio_library/)")
        console.print(" [bold cyan]2[/bold cyan] Download Lyrics for Playlist Text Files (playlist_sources/)")
        console.print(" [bold cyan]3[/bold cyan] Search & Download Lyrics for a Single Track")
        console.print(" [bold cyan]0[/bold cyan] Return to Main Menu")

        choice = Prompt.ask("\nSelect option", choices=["1", "2", "3", "0"], default="1")

        if choice == "1":
            sync_audio_library_lyrics()
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
