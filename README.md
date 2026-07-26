# Spotify - Apple Music Toolkit

An all-in-one interactive toolkit to tag local audio files (.mp3, .m4a), fix high-res cover art, download synchronized scrolling lyrics (.lrc), and automatically create official **Spotify** and **Apple Music** playlists directly from text files. Built for **Windows**, **macOS**, and **Linux**.

---

## Features Overview

- **Audio Tagger & Album Art Fixer (`audio_tagger.py` / `album_art_fixer.py`)**:
  - Automatically tags Title, Artist, Album, Genre, physical audio BPM (tempo), and Music Style/Mood.
  - High-res (1000x1000) studio cover art search & embedding with studio-album sanity scoring (filters out low-quality compilations).
  - Safeguard mode preserves existing tags.

- **Synchronized Lyrics Downloader (`lyrics_downloader.py`)**:
  - Downloads timestamped scrolling lyrics (`.lrc`) for music players (MusicBee, VLC, AIMP, Poweramp, Musicolet).
  - Clean standardized header formatting (`[ti:Title]`, `[ar:Artist]`, `[al:Album]`).

- **Spotify Playlist Creator (`playlist_creator.py`)**:
  - Converts text song lists into official Spotify playlists on your account via Spotipy API.
  - Generates backup `.m3u8` and `.xml` files in `playlist_exports/spotify/`.

- **Apple Music Playlist Creator (`apple_music_playlist_creator.py`)**:
  - **Direct Cloud API Sync:** Creates playlists directly in your official Apple Music account via Apple's official API (`amp-api.music.apple.com`) with zero third-party website dependency!
  - **Track Sanity Engine:** Intelligently avoids live versions, remixes, acoustic, cover, or compilation tracks unless requested.
  - **Smart Query Parsing:** Cleans truncated titles, unclosed brackets, and slash artist splits (e.g. `Dept / Oh Yun`, `United States of Pop`).
  - **Multi-Threaded Performance:** 5-worker concurrent searching with real-time Rich progress bar updates.
  - **Export Formats:** Generates native TSV (`_apple_playlist.txt`), `.xml`, and `.m3u8` in `playlist_exports/apple_music/`.

---

## Feature Documentation Guides

Detailed step-by-step guides for each feature are available in the **[`docs/`](file:///c:/GitHub/spotify-audio-toolkit/docs/)** folder:

- **[Apple Music Playlist Creator Guide](file:///c:/GitHub/spotify-audio-toolkit/docs/apple_music_guide.md)**
- **[Spotify Playlist Creator Guide](file:///c:/GitHub/spotify-audio-toolkit/docs/spotify_guide.md)**
- **[Audio Tagger & Album Art Fixer Guide](file:///c:/GitHub/spotify-audio-toolkit/docs/audio_tagger_guide.md)**
- **[Synchronized Lyrics Downloader Guide](file:///c:/GitHub/spotify-audio-toolkit/docs/lyrics_downloader_guide.md)**

---

## Multi-OS Setup Guide (Windows & macOS / Linux)

Follow these step-by-step instructions to set up the toolkit on your computer.

### Step 1: Install Python
- Ensure Python (version **3.10 or newer**) is installed on your computer.
- Download from: [https://www.python.org/downloads/](https://www.python.org/downloads/)
- *(On Windows, make sure to check the box: **"Add Python to PATH"**).*

### Step 2: Install Dependencies & Setup Virtual Environment

#### Windows:
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

#### macOS & Linux:
> [!NOTE]
> On macOS and Linux, Python 3 commands use `python3` and `pip3` instead of `python` and `pip`.

```bash
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
```

---

### Step 3: Configure Credentials & Network (`.env`)

Create a file named `.env` in the project root folder (or rename `.env.example` to `.env`).

#### A. Spotify Setup (Required for Option 2)
1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and log in with your free Spotify account.
2. Click **Create app**.
3. Fill in:
   - **App name:** `Music Toolkit`
   - **App description:** `Audio Tagging and Playlist Manager`
   - **Redirect URIs:** `https://127.0.0.1:8888/callback`
4. Save the app, click **Settings**, and copy your **Client ID** and **Client Secret**.

#### B. Apple Music Setup (Required for Option 3 Direct Cloud Sync)
1. Open **[https://music.apple.com](https://music.apple.com)** in your web browser (Chrome, Edge, Brave, or Safari) and log in.
2. Press **F12** (Developer Tools).
3. Go to the **Application** tab -> **Cookies** -> `https://music.apple.com`.
4. Locate and copy the value of **`media-user-token`**.

#### C. Network / Proxy Configuration (Optional for Multi-OS Networks)
If your network environment uses an HTTP or SOCKS proxy (such as in corporate networks or VPN setups), configure proxy environment variables in `.env`:
```env
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
NO_PROXY=localhost,127.0.0.1
```

#### D. Save `.env` File
Paste your Spotify, Apple Music, and network proxy credentials into `.env`:

```env
# Spotify Configuration
SPOTIPY_CLIENT_ID=your_spotify_client_id_here
SPOTIPY_CLIENT_SECRET=your_spotify_client_secret_here
SPOTIPY_REDIRECT_URI=https://127.0.0.1:8888/callback

# Apple Music Configuration (Direct Cloud Sync)
APPLE_MUSIC_USER_TOKEN=your_apple_music_media_user_token_here
```

---

## How to Use the Toolkit

### Step 1: Add Your Files
- **Audio Files:** Drop your `.mp3` or `.m4a` files into **`audio_library/`**.
- **Song Lists:** Drop any text file (`.txt`) containing song titles (one per line) into **`playlist_sources/source_text_files/`**.

  *Example text file format (`playlist_sources/source_text_files/international_songs.txt`):*
  ```text
  Back to December - Taylor Swift
  360 - Charli xcx
  21 Guns - Green Day
  Young Wild and Free - Snoop Dogg / Bruno Mars
  ```

### Step 2: Run Main Menu

#### Windows:
```powershell
python main.py
```

#### macOS / Linux:
```bash
python3 main.py
```

### Step 3: Interactive Options
```text
============================================================
              SPOTIFY - APPLE MUSIC TOOLKIT                 
============================================================

1. Complete Process Audio Library (Tagging, Cover Art, Lyrics)
2. Spotify Playlist Creator
3. Apple Music Playlist Creator
4. Separate Utilities Menu
0. Exit
```

- **Option 1 (Complete Process Audio Library):** Tags song metadata, calculates tempo (BPM), embeds high-res cover art, and downloads synchronized scrolling lyrics (`.lrc`).
- **Option 2 (Spotify Playlist Creator):** Converts text files in `playlist_sources/source_text_files/` into official Spotify playlists on your account.
- **Option 3 (Apple Music Playlist Creator):** Converts text files in `playlist_sources/source_text_files/` into official Apple Music playlists directly on your account and exports `.txt` TSV, `.xml`, and `.m3u8` to `playlist_exports/apple_music/`.
- **Option 4 (Utilities Menu):** Standalone access to Album Art Fixer, Audio Tagger, or Lyrics Downloader.

---

## Organized Directory & Folder Structure

The project directory structure is designed for simplicity and clarity for non-technical users:

```text
spotify-audio-toolkit/
├── main.py                         # Master Launcher Dashboard (Run this file)
│
├── audio_library/                  # Drop your local audio files (.mp3, .m4a) here
│   ├── Song.m4a                    # Audio file
│   └── Song.lrc                    # Synchronized lyrics file (auto-saved alongside audio)
│
├── playlist_sources/              # Input Folder
│   └── source_text_files/          # Drop text song list files (.txt) here
│       ├── international_songs.txt # Example text song list
│       └── local_songs.txt         # Example text song list
│
├── playlist_exports/              # Generated Playlist & Lyrics Exports
│   ├── apple_music/               # Exports for Apple Music (.txt TSV, .xml, .m3u8)
│   ├── spotify/                   # Exports for Spotify (.xml, .m3u8)
│   └── lyrics/                    # Standalone .lrc lyrics files extracted from text lists
│
├── reports/                        # Detailed Execution Reports & Summary Logs
│   ├── album_art_fixer_report.txt  # Cover art fixing log
│   ├── audio_tagging_report.txt    # Metadata & BPM tagging log
│   └── lyrics_download_report.txt  # Lyric search log
│
├── toolkit/                        # Modular Core Python Package
│   ├── core/                      # Config, paths, and network handling (sessions, proxies, HTTP)
│   ├── audio/                     # Audio tagging, BPM calculation, cover art & lyrics
│   ├── playlists/                 # Spotify & Apple Music playlist managers, parsers & exporters
│   └── ui/                        # Master CLI Dashboard & workspace status overview
│
├── main.py                        # Master Launcher Dashboard (Wrapper)
├── network_utils.py               # Network & proxy helper (Wrapper)
├── album_art_fixer.py             # Album Cover Art Fixer (Wrapper)
├── audio_tagger.py                # Audio Metadata & BPM Tagger (Wrapper)
├── lyrics_downloader.py           # Synchronized Lyrics Downloader (Wrapper)
├── playlist_creator.py            # Spotify Playlist Creator (Wrapper)
├── apple_music_playlist_creator.py# Apple Music Direct API Playlist Creator (Wrapper)
│
├── .env                           # API keys, user tokens & proxy settings
├── .env.example                   # Configuration template example
├── requirements.txt               # Dependencies list
└── README.md                      # Documentation & Guide
```

---

## FAQ & Troubleshooting

#### Q: How do I run commands on macOS?
**A:** macOS uses `python3` instead of `python`. Run `python3 main.py` or `python3 script_name.py`.

#### Q: Where are downloaded lyrics saved?
**A:** 
- For local audio tracks: `.lrc` files are saved directly alongside the `.mp3`/`.m4a` file in **`audio_library/`**.
- For text song lists: `.lrc` files are saved cleanly in **`playlist_exports/lyrics/`**.

#### Q: Where are report logs saved?
**A:** All generated text logs (`album_art_fixer_report.txt`, `audio_tagging_report.txt`, `lyrics_download_report.txt`) are saved in the **`reports/`** directory, keeping your input `playlist_sources/` folder completely clean.

#### Q: How do I configure a proxy for corporate or VPN networks?
**A:** Add `HTTP_PROXY=http://ip:port` and `HTTPS_PROXY=http://ip:port` into your `.env` file. `network_utils.py` automatically routes API requests through your proxy on Windows, macOS, and Linux.

---

## License
This project is open-source and free to use.
