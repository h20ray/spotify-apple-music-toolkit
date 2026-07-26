# Synchronized Lyrics Downloader Guide

The **Lyrics Downloader** module (`lyrics_downloader.py`) searches and downloads timestamped scrolling lyrics (`.lrc`) for local audio files and text song lists.

---

## Key Features

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
  [by:Spotify - Apple Music Toolkit]
  ```

### 3. Clear Storage Locations (Non-Tech Friendly)
- **Local Audio Files:** `.lrc` files are saved directly alongside the `.mp3`/`.m4a` file in **`audio_library/`** so music players automatically load them when playing songs.
- **Text Song Lists:** Lyrics for text song lists are saved cleanly in **`playlist_exports/lyrics/`**.
- **Execution Log:** Detailed report is saved to **`reports/lyrics_download_report.txt`**.

---

## How to Use

### 1. Add Files
- For local audio processing: Drop `.mp3` or `.m4a` files into **`audio_library/`**.
- For text song lists: Drop `.txt` files into **`playlist_sources/source_text_files/`**.

### 2. Run Main Menu

#### Windows:
```powershell
python main.py
```

#### macOS & Linux:
```bash
python3 main.py
```

- Select **Option 1 (Complete Process Audio Library)**: Automatically downloads `.lrc` files for every song in `audio_library/`.
- Select **Option 4 (Utilities Menu)** -> **Lyrics Downloader**: Fetch lyrics for specific songs or text lists.
