"""Apple Music playlist creator interactive menu and import orchestration."""
from __future__ import annotations

import os

from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from toolkit.core import APPLE_MUSIC_USER_TOKEN, EXPORT_APPLE_MUSIC_DIR
from toolkit.playlists.apple_music.cloud import create_apple_music_cloud_playlist
from toolkit.playlists.apple_music.search import (
    clear_search_cache_for_songs,
    ensure_folders,
    load_search_cache,
    process_track_batch,
)
from toolkit.playlists.apple_music.state import (
    EXPORT_FOLDER_NAME,
    SEARCH_CACHE,
    SOURCE_FOLDER_NAME,
    console,
)
from toolkit.playlists.exporter import export_apple_tsv, export_apple_xml, export_m3u8
from toolkit.playlists.parser import clean_string, parse_songs, pre_sanitize_song_line, scan_playlist_files


def display_header():
    """Display clean Apple Music Playlist Creator header banner."""
    console.clear()
    banner_text = """[bold bright_red]APPLE MUSIC PLAYLIST CREATOR[/bold bright_red]
Convert text song lists into official Apple Music playlists (Direct Cloud API).
Source: [bold magenta]{SOURCE_FOLDER_NAME}/[/bold magenta]
Export Destination: [bold green]{EXPORT_FOLDER_NAME}/[/bold green]"""
    console.print(Panel(banner_text, border_style="red", expand=False))


def import_file_to_apple_music(file_info, custom_name=None, auto_resume=False):
    """Process text file and generate Apple Music playlist outputs in playlist_exports/apple_music/."""
    ensure_folders()
    filename = file_info['filename']
    file_path = file_info['path']
    raw_songs = parse_songs(file_path)

    if not raw_songs:
        console.print(f"[bold yellow]Notice: '{filename}' contains no songs. Skipping.[/bold yellow]")
        return None

    cleaned_songs = [pre_sanitize_song_line(s) for s in raw_songs if pre_sanitize_song_line(s)]

    seen_keys = set()
    unique_songs = []
    for s in cleaned_songs:
        ckey = clean_string(s)
        if ckey and ckey not in seen_keys:
            seen_keys.add(ckey)
            unique_songs.append(s)

    def artist_sort_key(s):
        if ' - ' in s:
            parts = s.split(' - ', 1)
            return (clean_string(parts[0]), clean_string(parts[1]))
        return (clean_string(s), "")

    songs = sorted(unique_songs, key=artist_sort_key)
    dedup_removed = len(raw_songs) - len(songs)

    playlist_name = custom_name or os.path.splitext(filename)[0].replace('_', ' ').title()

    console.print(
        f"\n[bold green]Processing Apple Music Playlist:[/bold green] "
        f"[bold white]{playlist_name}[/bold white] "
        f"({len(songs)} unique songs)"
    )
    if dedup_removed > 0:
        console.print(
            f"[bold cyan]Pre-Sanitization Notice:[/bold cyan] Removed "
            f"[bold green]{dedup_removed}[/bold green] duplicate/invalid "
            f"entries ({len(raw_songs)} → {len(songs)} unique tracks)."
        )
    console.print("[dim green]Sorted all tracks alphabetically by Artist Name.[/dim green]\n")

    load_search_cache()
    cached_count = sum(1 for song in songs if song in SEARCH_CACHE)

    if cached_count > 0 and not auto_resume:
        console.print(
            f"[bold yellow]Cache Notice:[/bold yellow] Found cached search "
            f"results for [bold cyan]{cached_count}/{len(songs)}[/bold cyan] "
            f"tracks."
        )
        console.print(" [bold cyan]1[/bold cyan] Resume (Use cached searches - Fast)")
        console.print(
            " [bold cyan]2[/bold cyan] Fresh Start "
            "(Clear cache & search all fresh from API)"
        )
        cache_choice = Prompt.ask("\nSelect execution mode", choices=["1", "2"], default="1")

        if cache_choice == "2":
            clear_search_cache_for_songs(songs)
            console.print(
                "[dim yellow]Cache cleared for this playlist. "
                "Starting 100% fresh API search...[/dim yellow]\n"
            )
        else:
            console.print("[dim green]Resuming search using local cache...[/dim green]\n")

    console.print(
        "[dim]Applying track sanity scoring to select studio versions "
        "and filter out unwanted Live/Remix tracks...[/dim]\n"
    )

    found_tracks = []
    not_found = []

    try:
        with Progress(
            SpinnerColumn(),
            TaskProgressColumn(),
            BarColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Initializing Search...", total=len(songs))
            batch_results = process_track_batch(songs, progress=progress, task=task)
    except KeyboardInterrupt:
        console.print(
            f"[bold yellow]\nOperation aborted for '{playlist_name}'. "
            f"All searched tracks saved to cache.[/bold yellow]"
        )
        return None

    for song in songs:
        item = batch_results.get(song)
        if item:
            found_tracks.append((song, item))
        else:
            not_found.append(song)

    if not found_tracks:
        console.print(f"[bold red]Error: No matching songs found for '{playlist_name}'.[/bold red]")
        return None

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

    user_token = APPLE_MUSIC_USER_TOKEN
    if user_token:
        console.print(
            "\n[bold cyan]Found APPLE_MUSIC_USER_TOKEN in .env! "
            "Syncing directly to Apple Music Cloud...[/bold cyan]"
        )
        create_apple_music_cloud_playlist(playlist_name, matched_items, user_token)

    if not_found:
        extra = ""
        if len(not_found) > 15:
            extra = f"\n... and {len(not_found) - 15} more"
        console.print(
            Panel(
                "\n".join([f"- {item}" for item in not_found[:15]]) + extra,
                title=f"Unmatched Songs ({len(not_found)})",
                border_style="yellow",
            )
        )

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
        console.print()
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
            info_text = (
                "[bold yellow]DIRECT APPLE MUSIC CLOUD API CREATION "
                "(NO THIRD-PARTY WEBSITES)[/bold yellow]\n\n"
                "Python can push playlists directly into your Apple Music "
                "account via official Apple Music Cloud API!\n\n"
                "[bold green]Step-by-Step Setup (1-Time):[/bold green]\n"
                "1. Open [bold cyan]https://music.apple.com[/bold cyan] "
                "in Chrome / Edge / Brave and log in.\n"
                "2. Press [bold yellow]F12[/bold yellow] (DevTools) -> "
                "[bold yellow]Application[/bold yellow] tab -> "
                "[bold yellow]Cookies[/bold yellow] -> "
                "[bold cyan]https://music.apple.com[/bold cyan]\n"
                "3. Copy the value of [bold white]media-user-token"
                "[/bold white].\n"
                "4. Add it to your [bold white].env[/bold white] file:\n"
                "   [bold magenta]APPLE_MUSIC_USER_TOKEN="
                "your_copied_token_here[/bold magenta]\n\n"
                "Once added, Python will automatically create playlists "
                "directly inside your Apple Music account!"
            )
            console.print(Panel(info_text, border_style="blue"))
            Prompt.ask("\nPress Enter to return")

        elif choice == "0":
            break


def main():
    ensure_folders()
    interactive_menu()


if __name__ == "__main__":
    main()
