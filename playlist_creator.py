import os
import sys
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt, Confirm

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
console = Console()

SOURCE_FOLDER_NAME = "playlist_sources"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYLIST_SOURCES_DIR = os.path.join(BASE_DIR, SOURCE_FOLDER_NAME)

CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
REDIRECT_URI = os.getenv('SPOTIPY_REDIRECT_URI', 'http://127.0.0.1:8888/callback')
SCOPE = 'playlist-modify-public playlist-modify-private'

def ensure_source_folder():
    """Ensure the playlist sources directory exists."""
    if not os.path.exists(PLAYLIST_SOURCES_DIR):
        os.makedirs(PLAYLIST_SOURCES_DIR)

def get_spotify_client():
    """Authenticate and return Spotipy client instance."""
    if not CLIENT_ID or not CLIENT_SECRET:
        console.print("[bold red]Error:[/bold red] Missing SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET in .env configuration file.")
        sys.exit(0)
        
    auth_manager = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        open_browser=True
    )
    return spotipy.Spotify(auth_manager=auth_manager)

def scan_playlist_files():
    """Scan playlist_sources directory for text files and count total songs."""
    ensure_source_folder()
    files = [f for f in os.listdir(PLAYLIST_SOURCES_DIR) if f.lower().endswith('.txt')]
    files.sort()
    
    file_info_list = []
    for filename in files:
        full_path = os.path.join(PLAYLIST_SOURCES_DIR, filename)
        song_count = 0
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                c = line.strip()
                if c and not c.startswith("==="):
                    song_count += 1
        size_bytes = os.path.getsize(full_path)
        file_info_list.append({
            'filename': filename,
            'path': full_path,
            'song_count': song_count,
            'size': size_bytes
        })
    return file_info_list

def display_header(user_info=None):
    """Display clean application banner."""
    console.clear()
    user_str = f"[bold green]Account:[/bold green] {user_info['display_name']} ({user_info['id']})" if user_info else "[yellow]Authenticating...[/yellow]"
    
    banner_text = f"""[bold cyan]SPOTIFY PLAYLIST CREATOR[/bold cyan]
Convert text song lists into official Spotify playlists.
Folder: [bold magenta]{SOURCE_FOLDER_NAME}/[/bold magenta]
{user_str}"""
    console.print(Panel(banner_text, border_style="green", expand=False))

def parse_songs(file_path):
    """Parse track titles from text file."""
    songs = []
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("==="):
                songs.append(cleaned)
    return songs

def search_track(sp, song_line):
    """Search for track on Spotify."""
    if ' - ' in song_line:
        parts = song_line.split(' - ', 1)
        title, artist = parts[0].strip(), parts[1].strip()
        query = f"track:{title} artist:{artist}"
        try:
            results = sp.search(q=query, limit=1, type='track')
            items = results.get('tracks', {}).get('items', [])
            if items:
                return items[0]
        except Exception:
            pass
    
    try:
        results = sp.search(q=song_line, limit=1, type='track')
        items = results.get('tracks', {}).get('items', [])
        if items:
            return items[0]
    except Exception:
        pass
    
    return None

def import_file_to_spotify(sp, user_id, file_info, custom_name=None):
    """Process file and create Spotify playlist."""
    filename = file_info['filename']
    file_path = file_info['path']
    songs = parse_songs(file_path)
    
    if not songs:
        console.print(f"[bold yellow]Notice: '{filename}' contains no songs. Skipping.[/bold yellow]")
        return None

    playlist_name = custom_name or os.path.splitext(filename)[0].replace('_', ' ').title()

    console.print(f"\n[bold green]Creating Playlist:[/bold green] [bold white]{playlist_name}[/bold white] ({len(songs)} songs)")
    
    track_uris = []
    not_found = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Searching Spotify...", total=len(songs))
        
        for song in songs:
            progress.update(task, description=f"Searching: [dim]{song[:30]}...[/dim]")
            track = search_track(sp, song)
            if track:
                track_uris.append(track['uri'])
            else:
                not_found.append(song)
            progress.advance(task)

    if not track_uris:
        console.print(f"[bold red]Error: No matching songs found on Spotify for '{playlist_name}'.[/bold red]")
        return None

    playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=True)
    playlist_id = playlist['id']

    for i in range(0, len(track_uris), 100):
        batch = track_uris[i:i+100]
        sp.playlist_add_items(playlist_id, batch)

    table = Table(title=f"Summary: {playlist_name}", border_style="cyan")
    table.add_column("Property", style="bold white")
    table.add_column("Details", style="bold green")

    table.add_row("Total Listed Songs", str(len(songs)))
    table.add_row("Added to Spotify", f"{len(track_uris)} ({int(len(track_uris)/len(songs)*100)}%)")
    table.add_row("Unmatched Songs", str(len(not_found)))
    table.add_row("Playlist Web Link", f"[underline blue]{playlist['external_urls']['spotify']}[/underline blue]")

    console.print(table)

    if not_found:
        console.print(Panel(
            "\n".join([f"- {item}" for item in not_found[:15]]) + (f"\n... and {len(not_found)-15} more" if len(not_found) > 15 else ""),
            title=f"Unmatched Songs ({len(not_found)})",
            border_style="yellow"
        ))

    return playlist['external_urls']['spotify']

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

def interactive_menu(sp, user_info):
    """Run interactive menu loop."""
    user_id = user_info['id']

    while True:
        display_header(user_info)
        file_info_list = scan_playlist_files()

        console.print("[bold yellow]PLAYLIST CREATOR MENU:[/bold yellow]")
        console.print(" [bold cyan]1[/bold cyan] View Available Text Playlist Files")
        console.print(" [bold cyan]2[/bold cyan] Select One File to Create a Spotify Playlist")
        console.print(" [bold cyan]3[/bold cyan] Create Playlists for All Files (Batch Mode)")
        console.print(" [bold cyan]4[/bold cyan] User Guide")
        console.print(" [bold cyan]0[/bold cyan] Return to Main Menu")

        choice = Prompt.ask("\nSelect option", choices=["1", "2", "3", "4", "0"], default="1")

        if choice == "1":
            display_header(user_info)
            if not file_info_list:
                console.print(f"[bold yellow]No text files found in '{SOURCE_FOLDER_NAME}/'[/bold yellow]")
            else:
                list_files_table(file_info_list)
            Prompt.ask("\nPress Enter to return")

        elif choice == "2":
            display_header(user_info)
            if not file_info_list:
                console.print(f"[bold red]No text files found in '{SOURCE_FOLDER_NAME}/'.[/bold red]")
                Prompt.ask("\nPress Enter to return")
                continue

            list_files_table(file_info_list)
            valid_indices = [str(i) for i in range(1, len(file_info_list) + 1)]
            file_idx = Prompt.ask("\nSelect file index to import", choices=valid_indices)
            selected_file = file_info_list[int(file_idx) - 1]

            default_name = os.path.splitext(selected_file['filename'])[0].replace('_', ' ').title()
            custom_name = Prompt.ask("Spotify Playlist Name", default=default_name)

            import_file_to_spotify(sp, user_id, selected_file, custom_name=custom_name)
            Prompt.ask("\nPress Enter to return")

        elif choice == "3":
            display_header(user_info)
            if not file_info_list:
                console.print(f"[bold red]No text files found in '{SOURCE_FOLDER_NAME}/'.[/bold red]")
                Prompt.ask("\nPress Enter to return")
                continue

            list_files_table(file_info_list)
            if Confirm.ask(f"\nCreate Spotify playlists for all {len(file_info_list)} files?"):
                created_links = []
                for info in file_info_list:
                    link = import_file_to_spotify(sp, user_id, info)
                    if link:
                        created_links.append((info['filename'], link))
                
                if created_links:
                    console.print("\n[bold green]Batch Playlist Creation Complete![/bold green]")
                    for fname, link in created_links:
                        console.print(f"- [bold white]{fname}[/bold white]: [underline blue]{link}[/underline blue]")
            
            Prompt.ask("\nPress Enter to return")

        elif choice == "4":
            display_header(user_info)
            info_text = f"""[bold yellow]HOW TO USE PLAYLIST CREATOR[/bold yellow]

1. Place any text file (.txt) with song titles into:
   [bold magenta]{PLAYLIST_SOURCES_DIR}[/bold magenta]

2. Text File Format:
   Song Title - Artist Name  (or simply Song Title Artist Name)

3. The system will automatically search Spotify, create the playlist on your account,
   and output the direct link to listen!"""
            console.print(Panel(info_text, border_style="blue"))
            Prompt.ask("\nPress Enter to return")

        elif choice == "0":
            break

def main():
    ensure_source_folder()
    display_header()
    
    console.print(Panel(
        "[bold cyan]SPOTIFY ACCOUNT LOGIN[/bold cyan]\n"
        "[dim]Option 2 requires playlist creation permissions on your Spotify account.\n"
        "Your web browser will open automatically to authorize access.\n\n"
        "Important: Ensure 'http://127.0.0.1:8888/callback' is added in your Spotify Developer Dashboard under App Settings > Redirect URIs.\n"
        "If prompted, log in and copy the redirected URL back to the terminal.[/dim]",
        border_style="yellow"
    ))
    
    sp = get_spotify_client()
    user_info = sp.current_user()
    interactive_menu(sp, user_info)

if __name__ == '__main__':
    main()
