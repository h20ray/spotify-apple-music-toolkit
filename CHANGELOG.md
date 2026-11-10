# Changelog

## [Unreleased]

### Added
- **Album & Cover Fixer** (menu 8, `toolkit.audio.album_fixer` + `album_resolver`): finds the original studio album
  via iTunes, falls back to MusicBrainz when the iTunes score is below 70, writes `reports/album_fix_report.tsv`
  first and only changes files (album tag, year if empty, cover) after confirmation. Rows are CHANGE / REVIEW /
  NOT_FOUND / OK; only CHANGE is applied.
  Live progress (one line per song, ETA, rate-limit notices), results cached every 20 songs so a run can resume.
- Genius API as the **last-resort** album source (only when iTunes and MusicBrainz fail or are unsure) when
  `GENIUS_CLIENT_ID` and `GENIUS_CLIENT_SECRET` are set in `.env`; skipped otherwise. See
  `docs/album_cover_fixer_guide.md`.
- Track/disc numbers are taken from the original album (implausible iTunes numbers such as 138/163 are rejected).
- Non-interactive CLI: `python -m toolkit.audio.album_fixer --folder DIR [--full] [--apply clean|all]`.
  Before writing, the current album/year/track tags are saved to `reports/album_fix_backup_<time>.json`;
  `--restore FILE` puts them back (cover art is not backed up).

### Fixed
- Tagger mode 1 no longer protects a compilation/playlist album tag; it is replaced and the cover rewritten.
- Album Art Fixer no longer boosts covers matching a compilation album tag, and only considers iTunes results
  for the same song and artist.
- `score_album_quality` matched any album containing "ep" (e.g. "Sleep") as single/EP; now whole words only.
- Spotify studio-album pick prefers the earliest plain release over deluxe/reissue editions.
- Lint: removed extra blank lines in `parser.py` and `tests/test_parser.py` (flake8 is clean).

## [1.0.1] — 2026-07-27

### Changed
- Split large modules into packages:
  - `toolkit.playlists.apple_music` → scoring / search / cloud / menu / state
  - `toolkit.audio.tagger` → metadata_fetch / bpm / mood / writer / processor
  - `toolkit.audio.artwork` → sources / embed / processor
- Public imports unchanged (`toolkit.playlists.apple_music`, `toolkit.audio.tagger`, `toolkit.audio.artwork`)

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
