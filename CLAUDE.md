# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Interactive Rich-based CLI (Python 3.10+) for tagging a local audio library (title/artist/album/genre, BPM, mood, cover art, synced `.lrc` lyrics) and building Spotify / Apple Music playlists from plain-text song lists (`Title - Artist`, one per line). Entry point: `python main.py` → `toolkit.ui.dashboard.main()`. See `ARCHITECTURE.md` and `docs/` for per-feature guides.

## Commands

```bash
pip install -r requirements.txt && pip install -e ".[dev]"   # runtime + dev tools (pytest, black, isort, flake8, mypy)
python main.py                                               # interactive menu

pytest                                                       # all tests (config in pyproject: testpaths=tests, -q)
pytest tests/test_scoring.py::test_score_album_studio                 # single test
pytest --cov=toolkit

flake8 toolkit --max-line-length=120 --extend-ignore=E203,W503   # what CI lint runs (CI fails on this)
mypy toolkit                                                      # CI runs it but ignores failures
black . && isort .                                                # line length 120
```

CI (`.github/workflows/`) runs pytest on Python 3.10, 3.11 and 3.12 — avoid syntax newer than 3.10 (e.g. nested same-quote f-strings broke CI before).

## Architecture

- `toolkit/core` — `config.py` defines every project path (all derived from repo root `BASE_DIR`), loads `.env` at import time, and reads `config/keywords.json` (merged over `DEFAULT_KEYWORDS`, auto-created if missing). `network.py` provides a shared `requests.Session` with proxy (`HTTP_PROXY`/`HTTPS_PROXY`) and IPv4 fallback — use `http_get`/`http_post` rather than raw `requests`. Timeouts, worker counts, user agents and scoring magic numbers live in `constants.py`.
- `toolkit/audio` — `metadata.read_audio_metadata` is the single reader for MP3/M4A/FLAC tags; `tagger/` (Spotify metadata fetch → librosa BPM → mood → mutagen writer), `artwork/` (sources → resize → embed), `lyrics.py` (LRC download next to audio files). `album_resolver.py` finds a song's original album (iTunes, scored; MusicBrainz when the score is below 70; Genius only as the last resort, needs `GENIUS_CLIENT_ID`/`GENIUS_CLIENT_SECRET`) and `album_fixer.py` (menu 8 / `python -m toolkit.audio.album_fixer`) writes a TSV report, backs up tags to `reports/album_fix_backup_*.json`, then applies album/year/track/cover; see `docs/album_cover_fixer_guide.md`.
- `toolkit/playlists` — `parser` cleans/sanitizes song lines; `spotify.py` searches + creates via spotipy; `apple_music/` searches through a tiered fallback (local cache → iTunes Search API → Apple catalog `amp-api` → Deezer) scored by `scoring.score_track_candidate` using the keyword lists to reject karaoke/covers/remixes/live versions unless the line asks for them; `cloud.py` creates the library playlist using `APPLE_MUSIC_USER_TOKEN` plus a developer token scraped from music.apple.com JS (or `APPLE_MUSIC_DEVELOPER_TOKEN`). `exporter` writes TSV/M3U8/XML into `playlist_exports/`.
- `toolkit/ui/dashboard.py` — the only place that orchestrates menus and may call `sys.exit`; library modules must log/raise instead.

Conventions that span modules:
- Packages split into submodules re-export their public API from `__init__.py` (`toolkit.audio.tagger`, `toolkit.audio.artwork`, `toolkit.playlists.apple_music`); keep those exports stable. Root-level scripts (`audio_tagger.py`, `network_utils.py`, `playlist_creator.py`, etc.) are thin backward-compat wrappers over `toolkit`.
- Apple Music module-level mutable state (search cache, cached bearer token, rate-limit lock) lives in `apple_music/state.py`, held in one-element lists so submodules can mutate it.
- Tagger, artwork and lyrics run in `ThreadPoolExecutor`; progress/status updates must happen under `STATUS_LOCK`.
- Caches live in `.cache/` (`apple_music_search_cache.json`, `spotify_tag_cache.json`, `album_resolver_cache.json`, Spotify token).
- User output goes through a Rich `console`; warnings/errors through `toolkit.core.logging` (`get_logger`). Prefer specific exceptions over bare `except Exception`.
- Tests that touch paths use the `keywords_file` fixture in `tests/conftest.py`, which monkeypatches every path constant in `toolkit.core.config` to `tmp_path` — extend it if you add a new path constant.
- `playlist_sources/` and `playlist_exports/` contain the user's real data and are committed; don't regenerate or clean them unless asked.

---

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
rtk uv run <cmd>        # Compact uv project command output
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%). Format flags (-c, -l, -L, -o, -Z) run raw.
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->
