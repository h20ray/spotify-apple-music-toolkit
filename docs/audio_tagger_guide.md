# Audio Tagger & Album Art Fixer Guide

The **Audio Tagger** (`audio_tagger.py`) and **Album Art Fixer** (`album_art_fixer.py`) modules tag local audio files (`.mp3`, `.m4a`), calculate physical audio tempo (BPM), identify style/mood, and embed high-resolution 1000x1000 studio cover art into your music files.

---

## Key Features

### 1. High-Resolution Album Cover Art Fixer (`album_art_fixer.py`)
- Searches iTunes and music databases for official 1000x1000 high-res cover art.
- **Sanity Scoring Engine:** Prioritizes official studio albums over compilations, Various Artists, or low-quality single artwork.
- Embeds artwork cleanly into ID3v2 (MP3) and MP4 (M4A) metadata tags.

### 2. Physical Audio Tempo (BPM) Calculation
- Uses signal processing algorithms to analyze local audio waveforms.
- Computes exact physical beats per minute (BPM) without relying on web metadata.

### 3. Music Style & Mood Identification
- Classifies audio files into style/mood categories (e.g. Smooth & Chill, Energetic, Pop Style, Acoustic & Soft).

### 4. Safeguard Mode
- Preserves existing tags (Title, Artist, Album, Genre) and only fills in missing or empty metadata fields.

### 5. Detailed Execution Reports
- Writes full execution logs to **`reports/audio_tagging_report.txt`** and **`reports/album_art_fixer_report.txt`**, keeping `playlist_sources/` clean.

---

## How to Use

### 1. Add Audio Files
Place your `.mp3` or `.m4a` audio files into the **`audio_library/`** folder:
```text
audio_library/
├── Song1.mp3
└── Song2.m4a
```

### 2. Run Main Menu

#### Windows:
```powershell
python main.py
```

#### macOS & Linux:
```bash
python3 main.py
```

- Select **Option 1: Complete Process Audio Library** to tag metadata, calculate BPM, embed cover art, AND download lyrics in 1 click!
- Select **Option 4: Separate Utilities Menu** -> **Album Art Fixer** to only search and update album cover art.
