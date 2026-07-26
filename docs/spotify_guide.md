# Spotify Playlist Creator Guide

The **Spotify Playlist Creator** module (`playlist_creator.py`) converts text files containing song lists into official playlists directly on your **Spotify Account** using the official Spotipy API.

---

## 1-Time Setup Guide: Spotify Developer Credentials

To enable Spotify integration:

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and log in with your free Spotify account.
2. Click **Create app**.
3. Fill in the app details:
   - **App name:** `Music Toolkit`
   - **App description:** `Audio Tagging and Playlist Manager`
   - **Redirect URIs:** `https://127.0.0.1:8888/callback`
4. Click **Save**, then click **Settings**.
5. Copy your **Client ID** and **Client Secret**.
6. Open your project [**.env**](file:///c:/GitHub/spotify-audio-toolkit/.env) file and add your credentials:
   ```env
   SPOTIPY_CLIENT_ID=your_spotify_client_id_here
   SPOTIPY_CLIENT_SECRET=your_spotify_client_secret_here
   SPOTIPY_REDIRECT_URI=https://127.0.0.1:8888/callback
   ```

---

## How to Use

### 1. Add Text Song Lists
Place your text files (`.txt`) into the **`playlist_sources/source_text_files/`** directory:

```text
playlist_sources/source_text_files/
├── my_favorites.txt
└── workout_playlist.txt
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

Select **Option 2: Spotify Playlist Creator**.

### 3. Interactive Menu Options
- **View Available Text Files**: Scans and displays available song lists in `playlist_sources/source_text_files/`.
- **Select One File**: Converts a single text file into a Spotify playlist with custom name options.
- **Create All Files (Batch Mode)**: Processes all text files sequentially.
- **Public / Private Toggle**: Choose whether created playlists are Public or Private on your account.

---

## Network & Proxy Configuration (Multi-OS)

If running behind a corporate proxy or VPN, add proxy configurations to your `.env` file:
```env
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```
`network_utils.py` automatically configures Spotipy requests through your proxy.

---

## Export Backup Files

In addition to creating the playlist on your Spotify account, backup files are automatically saved in **`playlist_exports/spotify/`**:
- **`_spotify.m3u8`**: Standard M3U playlist file containing Spotify track URIs.
- **`_spotify.xml`**: XML formatted playlist backup.
