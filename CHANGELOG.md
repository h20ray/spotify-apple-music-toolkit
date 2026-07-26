# Changelog

## [1.0.0] — 2026-07-26

### Added
- Modular `toolkit` package layout (core / audio / playlists / ui)
- Central logging (`toolkit.core.logging`) with Rich handler
- Shared constants (`toolkit.core.constants`)
- Unified audio metadata reader (`toolkit.audio.metadata`)
- Spotify tag search cache (`.cache/spotify_tag_cache.json`)
- pytest suite for parser, exporter, scoring, mood, config, network, LRC, metadata
- GitHub Actions test + lint workflows
- `py.typed`, `pyproject.toml`, pre-commit config
- ARCHITECTURE / CONTRIBUTING docs

### Changed
- Library modules raise / log instead of `sys.exit` on missing Spotify creds (tagger)
- Thread progress advances under `STATUS_LOCK` (tagger, artwork, lyrics)
- Dependency pins use `~=` ranges
- Apple Music scoring / timeouts / penalties use shared constants
