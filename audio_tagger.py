import os
import sys
import logging
import warnings
import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

# Suppress internal warnings and HTTP logs
warnings.filterwarnings("ignore")
logging.getLogger('spotipy').setLevel(logging.CRITICAL)

import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TCON, TBPM, TXXX, TMOO, COMM, APIC, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
console = Console()

CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')
AUDIO_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_library")

COMPILATION_KEYWORDS = ["various artists", "compilation", "greatest hits", "best of", "now that's what i call", "top 100", "essential classics", "soundtrack"]

def get_spotify_client():
    """Authenticate with Spotify via API credentials."""
    if not CLIENT_ID or not CLIENT_SECRET:
        console.print("Error: Missing SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET in .env configuration file.")
        sys.exit(0)
    
    auth_mgr = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    return spotipy.Spotify(client_credentials_manager=auth_mgr)

def read_all_existing_metadata(file_path):
    """Read existing audio tags from local MP3 or M4A file."""
    f_lower = file_path.lower()
    meta = {
        'title': None,
        'artist': None,
        'album': None,
        'genre': None,
        'year': None,
        'bpm': 0,
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
                if 'TCON' in audio.tags and audio.tags['TCON'].text:
                    meta['genre'] = str(audio.tags['TCON'].text[0]).strip()
                if 'TDRC' in audio.tags and audio.tags['TDRC'].text:
                    meta['year'] = str(audio.tags['TDRC'].text[0]).strip()[:4]
                elif 'TYER' in audio.tags and audio.tags['TYER'].text:
                    meta['year'] = str(audio.tags['TYER'].text[0]).strip()[:4]
                if 'TBPM' in audio.tags and audio.tags['TBPM'].text:
                    try:
                        meta['bpm'] = int(round(float(str(audio.tags['TBPM'].text[0]).strip())))
                    except Exception:
                        pass
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
            if '\xa9gen' in audio and audio['\xa9gen']:
                meta['genre'] = str(audio['\xa9gen'][0]).strip()
            if '\xa9day' in audio and audio['\xa9day']:
                meta['year'] = str(audio['\xa9day'][0]).strip()[:4]
            if 'tmpo' in audio and audio['tmpo']:
                try:
                    meta['bpm'] = int(audio['tmpo'][0])
                except Exception:
                    pass
            meta['has_cover'] = ('covr' in audio and bool(audio['covr']))
        except Exception:
            pass

    return meta

def select_best_original_track(items):
    """Prioritizes official Studio Albums over Compilations and Various Artists collections."""
    if not items:
        return None
        
    studio_albums = []
    singles = []
    others = []

    for track in items:
        album = track.get('album', {})
        album_name = album.get('name', '').strip()
        album_type = album.get('album_type', '').lower()
        artists = track.get('artists', [])
        primary_artist = artists[0]['name'].lower() if artists else ""
        
        album_name_lower = album_name.lower()
        is_compilation = (
            album_type == 'compilation' or
            any(k in album_name_lower for k in COMPILATION_KEYWORDS) or
            'various' in primary_artist
        )

        if not is_compilation:
            if album_type == 'album':
                studio_albums.append(track)
            elif album_type == 'single':
                singles.append(track)
            else:
                others.append(track)
        else:
            others.append(track)

    if studio_albums:
        return studio_albums[0]
    elif singles:
        return singles[0]
    elif others:
        return others[0]
    return items[0]

def detect_physical_bpm(file_path):
    """Calculate exact physical song tempo (BPM) from audio signal."""
    try:
        import librosa
        y, sr = librosa.load(file_path, duration=30)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm_val = int(round(float(tempo[0] if hasattr(tempo, '__len__') else tempo)))
        return bpm_val
    except Exception:
        return 0

def calculate_mood(primary_genre="Pop"):
    """Derive clean text music mood style from genre."""
    genre_lower = primary_genre.lower()
    if any(k in genre_lower for k in ['dance', 'edm', 'house', 'rock', 'metal']):
        return "Energetic"
    elif any(k in genre_lower for k in ['indie', 'folk', 'acoustic', 'bedroom', 'chill']):
        return "Chill & Melancholic"
    elif any(k in genre_lower for k in ['r&b', 'soul', 'jazz', 'lo-fi', 'soft']):
        return "Smooth & Chill"
    else:
        return f"{primary_genre} Style"

def search_spotify_metadata(sp, query_text):
    """Fetch track details from Spotify API."""
    try:
        res = sp.search(q=query_text, limit=5, type='track')
        items = res.get('tracks', {}).get('items', [])
        if not items:
            return None

        track = select_best_original_track(items)
        if not track:
            return None
        
        primary_genre = "Pop"
        artist_id = track['artists'][0]['id']
        try:
            artist_info = sp.artist(artist_id)
            genres = artist_info.get('genres', [])
            if genres:
                primary_genre = genres[0].title()
        except Exception:
            pass

        mood = calculate_mood(primary_genre)

        cover_data = None
        images = track.get('album', {}).get('images', [])
        if images:
            img_url = images[0]['url']
            try:
                img_res = requests.get(img_url, timeout=10)
                if img_res.status_code == 200:
                    cover_data = img_res.content
            except Exception:
                pass

        year = ""
        release_date = track.get('album', {}).get('release_date', '')
        if release_date:
            year = release_date.split('-')[0]

        return {
            'title': track['name'],
            'artist': ", ".join([a['name'] for a in track['artists']]),
            'album': track['album']['name'],
            'genre': primary_genre,
            'year': year,
            'mood': mood,
            'cover_data': cover_data
        }
    except Exception as e:
        console.print(f"[dim red]Error fetching metadata for '{query_text}': {e}[/dim red]")
        return None

def tag_mp3_file(file_path, final_meta, write_cover=True):
    """Save audio tags to MP3 file."""
    try:
        try:
            audio = MP3(file_path, ID3=ID3)
        except ID3NoHeaderError:
            audio = MP3(file_path)
            audio.add_tags()

        if audio.tags is None:
            audio.add_tags()

        tags = audio.tags
        tags.add(TIT2(encoding=3, text=final_meta['title']))
        tags.add(TPE1(encoding=3, text=final_meta['artist']))
        tags.add(TALB(encoding=3, text=final_meta['album']))
        tags.add(TCON(encoding=3, text=final_meta['genre']))
        
        if final_meta['bpm'] > 0:
            tags.add(TBPM(encoding=3, text=str(final_meta['bpm'])))

        tags.add(TMOO(encoding=1, text=final_meta['mood']))
        tags.add(COMM(encoding=1, lang='eng', desc='', text=f"Mood: {final_meta['mood']}"))

        if write_cover and final_meta['cover_data']:
            tags.add(APIC(
                encoding=0,
                mime='image/jpeg',
                type=3,
                desc='Cover',
                data=final_meta['cover_data']
            ))

        # Save as ID3v2.3 for Windows File Explorer compatibility
        audio.save(v2_version=3)
        return True
    except Exception as e:
        console.print(f"[red]Failed to tag MP3 '{os.path.basename(file_path)}': {e}[/red]")
        return False

def tag_m4a_file(file_path, final_meta, write_cover=True):
    """Save audio tags to M4A file."""
    try:
        audio = MP4(file_path)
        audio['\xa9nam'] = final_meta['title']
        audio['\xa9ART'] = final_meta['artist']
        audio['\xa9alb'] = final_meta['album']
        audio['\xa9gen'] = final_meta['genre']
        
        if final_meta['year']:
            audio['\xa9day'] = final_meta['year']

        if final_meta['bpm'] > 0:
            audio['tmpo'] = [final_meta['bpm']]

        audio['----:com.apple.iTunes:MOOD'] = final_meta['mood'].encode('utf-8')
        audio['\xa9cmt'] = [f"Mood: {final_meta['mood']}"]

        if write_cover and final_meta['cover_data']:
            audio['covr'] = [MP4Cover(final_meta['cover_data'], imageformat=MP4Cover.FORMAT_JPEG)]

        audio.save()
        return True
    except Exception as e:
        console.print(f"[red]Failed to tag M4A '{os.path.basename(file_path)}': {e}[/red]")
        return False

def select_tagging_mode():
    """Prompt user for Tagging Mode selection."""
    console.print("\n[bold yellow]TAG PROTECTION SETTINGS:[/bold yellow]")
    console.print(" [bold cyan]1[/bold cyan] [bold green]Safeguard Mode (Fill missing tags only - Protect existing tags)[/bold green] [Recommended]")
    console.print(" [bold cyan]2[/bold cyan] Overwrite Mode (Replace all tags with Spotify data)")
    
    choice = Prompt.ask("\nSelect Mode", choices=["1", "2"], default="1")
    return choice

def process_audio_folder(folder_path, mode=None):
    """Scan audio_library folder, calculate BPM, and update audio metadata tags."""
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

    sp = get_spotify_client()

    console.print(f"\n[bold green]Found {len(audio_files)} audio file(s) in {os.path.basename(folder_path)}/[/bold green]")
    
    if not mode:
        mode = select_tagging_mode()

    summary_table = Table(title="Audio Tagging Summary", border_style="cyan", header_style="bold magenta")
    summary_table.add_column("Audio File", style="bold white")
    summary_table.add_column("Title & Artist", style="green")
    summary_table.add_column("Album", style="cyan")
    summary_table.add_column("Tempo (BPM)", justify="right", style="bold yellow")
    summary_table.add_column("Status", style="dim")
    report_rows = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Processing audio files...", total=len(audio_files))

        for fname in audio_files:
            file_path = os.path.join(folder_path, fname)
            file_base = os.path.splitext(fname)[0]

            existing = read_all_existing_metadata(file_path)

            query = f"{existing['title']} {existing['artist']}".strip() if (existing['title'] and existing['artist']) else file_base.replace('_', ' ')
            progress.update(task, description=f"Processing: [dim]{query[:25]}...[/dim]")

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

            if success:
                summary_table.add_row(
                    fname,
                    f"{final_title} - {final_artist}",
                    final_album,
                    f"{bpm_val} BPM" if bpm_val > 0 else "-",
                    action_desc
                )
                report_rows.append(f"{fname} | {final_title} - {final_artist} | {final_album} | {final_genre} | {final_mood} | {bpm_val} BPM | {action_desc}")
            else:
                summary_table.add_row(fname, "[dim red]Failed[/dim red]", "-", "-", "-")
                report_rows.append(f"{fname} | FAILED")

            progress.advance(task)

    console.print(summary_table)

    # Save report to text file
    try:
        report_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playlist_sources")
        if not os.path.exists(report_dir):
            os.makedirs(report_dir)
        report_path = os.path.join(report_dir, "audio_tagging_report.txt")
        
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(report_path, "w", encoding="utf-8") as rf:
            rf.write(f"=== AUDIO TAGGING REPORT ===\n")
            rf.write(f"Date & Time: {timestamp}\n")
            rf.write(f"Total Processed Tracks: {len(audio_files)}\n\n")
            rf.write("FILE NAME | TITLE & ARTIST | ALBUM | GENRE | MOOD/STYLE | TEMPO (BPM) | STATUS\n")
            rf.write("-" * 80 + "\n")
            for row in report_rows:
                rf.write(f"{row}\n")
        
        console.print(f"\n[bold green]Report saved to:[/bold green] [underline magenta]playlist_sources/audio_tagging_report.txt[/underline magenta]")
    except Exception as e:
        console.print(f"[dim yellow]Notice: Could not write report file: {e}[/dim yellow]")

def main():
    console.clear()
    console.print(Panel(
        "[bold cyan]AUDIO TAG & MOOD TAGGER[/bold cyan]\n"
        "[bold green]Updates song tags, calculates song tempo (BPM), and embeds album artwork.[/bold green]",
        border_style="green"
    ))
    
    process_audio_folder(AUDIO_FOLDER)

if __name__ == '__main__':
    main()
