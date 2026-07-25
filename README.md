# Spotify & Audio Music Toolkit

An all-in-one interactive toolkit to tag local audio files (.mp3, .m4a), fix high-res cover art, download synchronized scrolling lyrics (.lrc), and automatically create official **Spotify** and **Apple Music** playlists directly from text files.

---

## 🚀 Features Overview

- **🎵 Audio Tagger & Album Art Fixer (`audio_tagger.py` / `album_art_fixer.py`)**:
  - Automatically tags Title, Artist, Album, Genre, physical audio BPM (tempo), and Music Style/Mood.
  - High-res (1000x1000) studio cover art search & embedding with studio-album sanity scoring (filters out low-quality compilations).
  - Safeguard mode preserves existing tags.

- **🎤 Synchronized Lyrics Downloader (`lyrics_downloader.py`)**:
  - Downloads timestamped scrolling lyrics (`.lrc`) for music players (MusicBee, VLC, AIMP, Poweramp, Musicolet).
  - Clean standardized header formatting (`[ti:Title]`, `[ar:Artist]`, `[al:Album]`).

- **🎧 Spotify Playlist Creator (`playlist_creator.py`)**:
  - Converts text song lists into official Spotify playlists on your account via Spotipy API.
  - Generates backup `.m3u8` and `.xml` files in `playlist_exports/spotify/`.

- **🍎 Apple Music Playlist Creator (`apple_music_playlist_creator.py`)**:
  - **Direct Cloud API Sync:** Creates playlists directly in your official Apple Music account via Apple's official API (`amp-api.music.apple.com`) with zero third-party website dependency!
  - **Track Sanity Engine:** Intelligently avoids live versions, remixes, acoustic, cover, or compilation tracks unless requested.
  - **Smart Query Parsing:** Cleans truncated titles, unclosed brackets, and slash artist splits (e.g. `Dept / Oh Yun`, `United States of Pop`).
  - **Multi-Threaded Performance:** 5-worker concurrent searching with real-time Rich progress bar updates.
  - **Export Formats:** Generates native TSV (`_apple_playlist.txt`), `.xml`, and `.m3u8` in `playlist_exports/apple_music/`.

---

## 📚 Feature Documentation Guides

Detailed step-by-step guides for each feature are available in the **[`docs/`](file:///c:/GitHub/spotify-audio-toolkit/docs/)** folder:

- 🍎 **[Apple Music Playlist Creator Guide](file:///c:/GitHub/spotify-audio-toolkit/docs/apple_music_guide.md)**
- 🎧 **[Spotify Playlist Creator Guide](file:///c:/GitHub/spotify-audio-toolkit/docs/spotify_guide.md)**
- 🎵 **[Audio Tagger & Album Art Fixer Guide](file:///c:/GitHub/spotify-audio-toolkit/docs/audio_tagger_guide.md)**
- 🎤 **[Synchronized Lyrics Downloader Guide](file:///c:/GitHub/spotify-audio-toolkit/docs/lyrics_downloader_guide.md)**

---

## 📋 First-Time Setup Guide

Follow these step-by-step instructions to set up the toolkit on your computer.

### Step 1: Install Python
1. Ensure Python (version **3.10 or newer**) is installed on your computer.
2. Download from: [https://www.python.org/downloads/](https://www.python.org/downloads/)
3. *(During installation on Windows, make sure to check the box: **"Add Python to PATH"**).*

### Step 2: Install Dependencies
Open Windows PowerShell or Command Prompt in the project directory and run:

```powershell
pip install -r requirements.txt
```

---

### Step 3: Configure Credentials (`.env`)

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
1. Open **[https://music.apple.com](https://music.apple.com)** in your web browser (Chrome, Edge, or Brave) and log in.
2. Press **F12** (Developer Tools).
3. Go to the **Application** tab → **Cookies** → `https://music.apple.com`.
4. Locate and copy the value of **`media-user-token`**.

#### C. Save `.env` File
Paste both your Spotify and Apple Music credentials into `.env`:

```env
# Spotify Configuration
SPOTIPY_CLIENT_ID=your_spotify_client_id_here
SPOTIPY_CLIENT_SECRET=your_spotify_client_secret_here
SPOTIPY_REDIRECT_URI=https://127.0.0.1:8888/callback

# Apple Music Configuration (Direct Cloud Sync)
APPLE_MUSIC_USER_TOKEN=your_apple_music_media_user_token_here
```

---

## 🛠️ How to Use the Toolkit

### Step 1: Add Your Files
- **Audio Files:** Drop your `.mp3` or `.m4a` files into **`audio_library/`**.
- **Song Lists:** Drop any text file (`.txt`) containing song titles (one per line) into **`playlist_sources/`**.

  *Example text file format (`playlist_sources/international_songs.txt`):*
  ```text
  Back to December - Taylor Swift
  360 - Charli xcx
  21 Guns - Green Day
  Young Wild and Free - Snoop Dogg / Bruno Mars
  ```

### Step 2: Run Main Menu
Open PowerShell or Terminal and execute:

```powershell
python main.py
```

### Step 3: Interactive Options
```text
============================================================
              SPOTIFY & AUDIO MUSIC TOOLKIT                 
============================================================

1. Complete Process Audio Library (Tagging, Cover Art, Lyrics)
2. Spotify Playlist Creator
3. Apple Music Playlist Creator
4. Separate Utilities Menu
0. Exit
```

- **Option 1 (Complete Process Audio Library):** Tags song metadata, calculates tempo (BPM), embeds high-res cover art, and downloads synchronized scrolling lyrics (`.lrc`).
- **Option 2 (Spotify Playlist Creator):** Converts text files in `playlist_sources/` into official Spotify playlists on your account.
- **Option 3 (Apple Music Playlist Creator):** Converts text files in `playlist_sources/` into official Apple Music playlists directly on your account and exports `.txt` TSV, `.xml`, and `.m3u8` to `playlist_exports/apple_music/`.
- **Option 4 (Utilities Menu):** Standalone access to Album Art Fixer, Audio Tagger, or Lyrics Downloader.

---

## 📁 Directory & Folder Structure

```text
spotify-audio-toolkit/
├── main.py                         # Master Launcher Dashboard (Run this file)
│
├── audio_library/                  # Drop your local audio files (.mp3, .m4a) here
│   ├── Song.m4a                    # Audio file
│   └── Song.lrc                    # Synchronized lyrics file (auto-saved)
│
├── playlist_sources/              # Drop text song list files (.txt) here
│   └── international_songs.txt    # Example text list
│
├── playlist_exports/              # Generated playlist export files
│   ├── apple_music/               # Exports for Apple Music (.txt TSV, .xml, .m3u8)
│   └── spotify/                   # Exports for Spotify (.xml, .m3u8)
│
├── album_art_fixer.py             # Module: High-Res Album Cover Art Fixer
├── audio_tagger.py                # Module: Metadata, BPM & Mood Tagger
├── lyrics_downloader.py           # Module: Synchronized Lyrics Downloader (.lrc)
├── playlist_creator.py            # Module: Spotify Playlist Creator
├── apple_music_playlist_creator.py# Module: Apple Music Direct API Playlist Creator
│
├── .env                           # API keys & user token credentials
├── .env.example                   # Configuration template example
├── requirements.txt               # Dependencies list
└── README.md                      # Documentation & Guide
```

---

## ❓ FAQ & Troubleshooting

#### Q: How do I know if Apple Music Direct Cloud Sync worked?
**A:** When running Option 3, you will see real-time progress messages:
```text
Playlist Container Created! (ID: p.JL68rYEsbmPv55K)
Synced 20/177 tracks to Apple Music Cloud...
...
✓ SUCCESS! Playlist 'International Songs' (177 tracks) synced directly to your Apple Music Account!
```
Open the Apple Music app on your PC, iPhone, or Mac, and the playlist will be instantly available in your library!

#### Q: Does Apple Music Playlist Creator avoid live versions or remixes?
**A:** Yes! The built-in sanity scoring engine penalizes live tracks (`-50 pts`), unwanted remixes (`-40 pts`), and compilations (`-15 pts`), while granting bonuses to official studio album tracks (`+40 pts`).

#### Q: Can I use this on Mac or Linux?
**A:** Yes! The toolkit runs cross-platform on Windows, macOS, and Linux.

---

## 📄 License
This project is open-source and free to use.
