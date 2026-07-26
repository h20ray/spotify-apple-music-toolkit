# Apple Music Playlist Creator Guide

The **Apple Music Playlist Creator** module (`apple_music_playlist_creator.py`) converts text files containing song lists into official playlists directly inside your **Apple Music Account** (Cloud Sync) without needing third-party websites or desktop app playlist imports.

---

## 1-Time Setup Guide: Getting Your Apple Music Token

To allow Python to create playlists directly in your Apple Music account, retrieve your `media-user-token` once:

1. Open your web browser (Chrome, Edge, Brave, or Safari) and go to **[https://music.apple.com](https://music.apple.com)**.
2. Log in with your **Apple ID** (Apple Music subscription account).
3. Press **F12** on your keyboard to open Developer Tools.
4. Click on the **Application** tab at the top bar.
5. In the left sidebar menu, expand **Cookies** and click on **`https://music.apple.com`**.
6. Find **`media-user-token`** in the list and double-click its value to copy it.
7. Open your project [**.env**](file:///c:/GitHub/spotify-audio-toolkit/.env) file and add your token:
   ```env
   APPLE_MUSIC_USER_TOKEN=paste_your_copied_token_here
   ```

---

## How to Use

### 1. Add Text Song Lists
Place your text files (`.txt`) into the **`playlist_sources/source_text_files/`** directory.
Each line should be a song name, optionally with the artist name:

*Example: `playlist_sources/source_text_files/international_songs.txt`*
```text
Back to December - Taylor Swift
360 - Charli xcx
21 Guns - Green Day
Always - Daniel Caesar
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

Select **Option 3: Apple Music Playlist Creator**.

---

## Network & Proxy Configuration (Multi-OS)

If running behind a corporate or VPN proxy, add proxy settings to your `.env` file:
```env
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```
`network_utils.py` automatically routes Apple Music API requests through your proxy.

---

## Advanced Features

### 1. Official Apple Music Catalog Engine
Queries Apple Music's official Catalog API (`amp-api.music.apple.com/v1/catalog/us/search`) to retrieve exact Apple Music Catalog Song IDs with zero rate-limit blocks.

### 2. Studio Album Track Sanity Filter
Automatically scores candidate tracks to prioritize studio albums and filter out unwanted versions:
- **Studio Album Match:** `+40 pts`
- **Live Version:** `-50 pts` (Avoided unless explicitly requested in title)
- **Unwanted Remix:** `-40 pts`
- **Compilation / Various Artists:** `-15 pts`

### 3. Smart Query Parsing
Cleans common text list formatting issues:
- Unclosed brackets (e.g. `Thnks fr th Mmrs (T` → `Thnks fr th Mmrs`)
- Slash artist splits (e.g. `Dept / Oh Yun` → `Dept`)
- Truncated titles (e.g. `United States of Po` → `United States of Pop`)

### 4. Backup Playlist Export Formats
All generated playlists automatically export backup files to **`playlist_exports/apple_music/`**:
- **`_apple_playlist.txt`**: Native Apple Music TSV Text Playlist format.
- **`_apple_music.xml`**: iTunes / Apple Music Library XML format.
- **`_apple_music.m3u8`**: UTF-8 Extended M3U format.
