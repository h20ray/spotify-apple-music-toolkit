# Architecture — Spotify-Apple Music Toolkit

## Overview

Interactive CLI toolkit for local audio tagging, album art, synced lyrics, and Spotify/Apple Music playlist creation.

```
main.py
  └── toolkit.ui.dashboard          # Rich menu / orchestration
        ├── toolkit.audio.*         # tagger, artwork, lyrics, metadata
        ├── toolkit.playlists.*     # spotify, apple_music, parser, exporter
        └── toolkit.core.*          # config, network, logging, constants
```

## Packages

| Package | Role |
|---------|------|
| `toolkit.core` | Paths, env, HTTP session/proxy, logging, shared constants |
| `toolkit.audio` | Unified metadata reader; tagger (Spotify + BPM + mood); artwork; LRC lyrics |
| `toolkit.playlists` | Text → playlist for Spotify & Apple Music; parse/sanitize; export TSV/M3U8/XML |
| `toolkit.ui` | Dashboard menu only |

## Data flow

1. **Config** — `.env` + `config/keywords.json` via `toolkit.core.config`
2. **Network** — shared `requests.Session` + proxy/IPv4 fallback
3. **Audio** — `metadata.read_audio_metadata` is single source; tagger/artwork/lyrics wrappers
4. **Playlists** — `parser` cleans lines → provider search with scoring → optional cloud create → `exporter`
5. **Cache** — `.cache/apple_music_search_cache.json`, `.cache/spotify_tag_cache.json`

## Threading

Tagger, artwork, and lyrics use `ThreadPoolExecutor` with `STATUS_LOCK` around progress/status updates.

## Entry

```text
python main.py  →  toolkit.ui.dashboard.main()
```
