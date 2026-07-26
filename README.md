# Spotify - Apple Music Toolkit

CLI toolkit for local audio files and playlists:

- Tag tracks (title, artist, album, genre, BPM, mood)
- Embed high-res cover art
- Download synced `.lrc` lyrics
- Build **Spotify** / **Apple Music** playlists from plain text lists

Works on **Windows**, **macOS**, and **Linux**.

## Real-world use

Prepare a media library before upload or airplay:

- **AzuraCast / radio automation** — clean tags + cover art so the station library sorts and displays correctly
- **DJ / personal library** — batch-fix messy downloads, then push playlists to Spotify or Apple Music
- **Offline players** — MusicBee, VLC, AIMP, Poweramp — drop `.lrc` next to audio for scrolling lyrics

## Quick start

1. **Python 3.10+** — [python.org](https://www.python.org/downloads/) (Windows: check *Add to PATH*)

2. **Install**

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

```bash
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
```

3. **Config** — copy `.env.example` → `.env` and fill keys you need:

| Need | Variable |
|------|----------|
| Spotify playlists / tagging | `SPOTIPY_CLIENT_ID`, `SPOTIPY_CLIENT_SECRET` |
| Apple Music cloud playlists | `APPLE_MUSIC_USER_TOKEN` |
| Proxy (optional) | `HTTP_PROXY`, `HTTPS_PROXY` |

Spotify keys: [Developer Dashboard](https://developer.spotify.com/dashboard) → create app → redirect `https://127.0.0.1:8888/callback`.

Apple Music token: [music.apple.com](https://music.apple.com) → F12 → Application → Cookies → `media-user-token`.

4. **Files**

- Audio → `audio_library/`
- Song lists (one line each) → `playlist_sources/source_text_files/`

```text
Back to December - Taylor Swift
360 - Charli xcx
21 Guns - Green Day
```

5. **Run**

```powershell
python main.py
```

```bash
python3 main.py
```

## Menu

```text
1  Complete Process Audio Library   (tag + BPM + mood + lyrics)
2  Spotify Playlist Creator
3  Apple Music Playlist Creator
4  Audio Tagger
5  Synced Lyrics Downloader
6  Album Art Fixer
7  Workspace status

0  Exit
```

## Folders

| Path | Role |
|------|------|
| `audio_library/` | Your tracks (and `.lrc` beside them) |
| `playlist_sources/source_text_files/` | Input song lists |
| `playlist_exports/` | Spotify / Apple Music / lyrics exports |
| `reports/` | Run logs |
| `toolkit/` | App code |

## Guides

More detail in [`docs/`](docs/):

- [Audio tagger & album art](docs/audio_tagger_guide.md)
- [Lyrics](docs/lyrics_downloader_guide.md)
- [Spotify playlists](docs/spotify_guide.md)
- [Apple Music playlists](docs/apple_music_guide.md)

## License

Open source — free to use.
