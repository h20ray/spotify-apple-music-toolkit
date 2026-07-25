# 🎤 Synchronized Lyrics Downloader Guide

The **Lyrics Downloader** module (`lyrics_downloader.py`) searches and downloads timestamped scrolling lyrics (`.lrc`) for local audio files and text song lists.

---

## 🚀 Key Features

### 1. Synchronized LRC File Generation
- Downloads timestamped lines (e.g. `[00:12.34] Line of lyrics...`) compatible with modern music players:
  - **Windows / Mac:** MusicBee, VLC, AIMP, Foobar2000
  - **Android / iOS:** Poweramp, Musicolet, GoneMAD, Retro Music Player

### 2. Standard Header Formatting
- Automatically formats standard LRC metadata headers:
  ```text
  [ti:Song Title]
  [ar:Artist Name]
  [al:Album Name]
  [by:Spotify & Audio Toolkit]
  ```

### 3. Dual Storage Locations
- **Local Audio Files:** `.lrc` files are saved directly alongside the `.mp3`/`.m4a` file in **`audio_library/`**.
- **Text Song Lists:** Lyrics for text song lists are saved in **`playlist_sources/lyrics/`**.

---

## 📝 How to Use

### 1. Process Local Audio Files
Run `main.py` -> **Option 1 (Complete Process Audio Library)**. It will automatically download `.lrc` files for every song in `audio_library/`.

### 2. Standalone Lyrics Downloader
Run `main.py` -> **Option 4 (Utilities Menu)** -> **Lyrics Downloader** to fetch lyrics for specific songs or text lists.
