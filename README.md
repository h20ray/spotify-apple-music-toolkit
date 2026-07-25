# Spotify & Audio Music Toolkit

An all-in-one interactive toolkit to create Spotify playlists from text files, update song metadata (title, artist, album, genre, tempo, mood, album cover art), and download synchronized scrolling lyrics (.lrc).

---

## First Time Setup Guide

Follow these simple steps to set up the toolkit on your computer.

### Step 1: Install Python
Ensure Python (version 3.10 or newer) is installed on your system.  
Download from: [https://www.python.org/downloads/](https://www.python.org/downloads/)  
*(During installation on Windows, check the box: **"Add Python to PATH"**).*

### Step 2: Install Required Packages
Open Windows PowerShell or Command Prompt in this folder and run:

```powershell
pip install -r requirements.txt
```

---

### Step 3: Get Free Spotify Credentials

To enable Spotify integration:

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and log in with your free Spotify account.
2. Click **Create app**.
3. Fill in:
   - **App name:** `Music Toolkit`
   - **App description:** `Audio Tagging and Playlist Manager`
   - **Redirect URIs:** `https://127.0.0.1:8888/callback`
4. Save the app and click **Settings**.
5. Copy your **Client ID** and **Client Secret**.

---

### Step 4: Create Your Credentials File (.env)

In this project folder, create a file named `.env` (or copy `.env.example` and rename it to `.env`).

Paste your Client ID and Client Secret into `.env`:

```env
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_SECRET=your_client_secret_here
SPOTIPY_REDIRECT_URI=https://127.0.0.1:8888/callback
```

---

## How to Use the Toolkit

### Step 1: Add Your Files
- **Music Files:** Place your `.mp3` or `.m4a` audio files into the **`audio_library/`** folder.
- **Song Lists:** Place any text files (`.txt`) with lists of songs into the **`playlist_sources/`** folder.

### Step 2: Run the Main Menu
Run this command in PowerShell or Terminal:

```powershell
python main.py
```

### Step 3: Select Your Action
- **Option 1 (Complete Process Audio Library):** Executes song metadata tagging, physical song tempo (BPM) calculation, music style/mood tagging, high-res album cover embedding, AND synchronized scrolling lyrics (.lrc) downloading in 1 click!
- **Option 2 (Spotify Playlist Creator):** Converts your text song lists into official Spotify playlists on your account.

---

## Folder & Module Structure

```text
mysterious-bell/
├── main.py                     # Master Launcher Dashboard (Run this file)
│
├── audio_library/              # Drop your local audio files (.mp3, .m4a) here
│   ├── Song.m4a                # Audio file
│   └── Song.lrc                # Synchronized lyrics file (saved automatically)
│
├── playlist_sources/          # Drop text song list files (.txt) here
│   ├── local_songs.txt        # Example text list
│   └── lyrics/                # Saved lyrics for text song lists
│
├── audio_tagger.py            # Module: Tags Title, Artist, Album, Genre, BPM, Mood & Cover Art
├── lyrics_downloader.py       # Module: Downloads synchronized scrolling lyrics (.lrc)
├── playlist_creator.py        # Module: Converts text files to Spotify playlists
│
├── .env                        # Credentials file (stores your private API keys)
├── .env.example                # Configuration template example
├── requirements.txt            # Package dependencies list
└── README.md                  # Instructions guide
```

---

## Modular Features Overview

### 1. Audio Tagger (`audio_tagger.py`)
- **Safeguard Mode:** Keeps your existing audio tags (Title, Artist, Album, Genre, Album Art) intact and fills missing fields only.
- **Studio Album Prioritization:** Filters out compilations and "Various Artists" albums to prioritize official studio albums.
- **Offline BPM Calculation:** Calculates exact song tempo (beats per minute) directly from audio signals offline.
- **Music Style (Mood):** Identifies the song style (e.g. Smooth & Chill, Energetic, Pop Style).

### 2. Lyrics Downloader (`lyrics_downloader.py`)
- Downloads timestamped scrolling lyrics formatted for music players (MusicBee, VLC, AIMP, Poweramp, Musicolet).
- Automatically formats standard headers: `[ti:Title]`, `[ar:Artist]`, `[al:Album]` with no extra spacing.

### 3. Playlist Creator (`playlist_creator.py`)
- Scans text files in `playlist_sources/`, matches songs on Spotify, and creates public/private playlists on your account.
