# Album & Cover Fixer Guide

Menu option **8** (`toolkit/audio/album_fixer.py`). It fixes tracks whose **album tag and cover art come from a
compilation or playlist** ("Millennium Pop Hits", "Summer Hits 2024", "Soft 00s", ...) instead of the original
album. It replaces them with the song's original album, year, track/disc number and a 1000x1000 cover.

It never changes title or artist, and it writes a report **before** touching any file.

---

## Where the original album comes from

Sources are tried in this order. Each later source is only used when the earlier ones fail or are unsure.

| Order | Source | Used when | Needs |
|-------|--------|-----------|-------|
| 1 | **iTunes Search API** | Always tried first. Accepted when its score is 70 or higher. | nothing |
| 2 | **MusicBrainz** | iTunes score is below 70, the song was not found, or iTunes only has a single/EP. Picks the earliest official studio album (no live, compilation or soundtrack type). | nothing |
| 3 | **Genius API** | **Last resort**: iTunes and MusicBrainz both failed, or MusicBrainz only found a reissue. | `GENIUS_CLIENT_ID`, `GENIUS_CLIENT_SECRET` in `.env` |

Without the Genius keys the third step is simply skipped; nothing else changes.

**iTunes score** starts at 100 and drops for: compilation or soundtrack album (-60), live/demo/version when the
title does not ask for it (-50), single/EP (-15), deluxe/remaster edition (-5). It goes up when the release year
matches the file's year (+10). The same song by the same artist is required.

### Genius setup (optional)

1. Create an API client at <https://genius.com/api-clients>.
2. Put the **Client ID** and **Client Secret** in `.env`:

```text
GENIUS_CLIENT_ID=...
GENIUS_CLIENT_SECRET=...
```

`.env` is git-ignored; `.env.example` only lists the variable names.

---

## Run it

```powershell
python main.py        # choose 8
```

1. Enter the folder (subfolders are included).
2. Choose **fast** (only songs whose album looks like a compilation/playlist, roughly half the lookups) or **full**
   (every song).
3. Watch the live log: one line per song, elapsed time and ETA, and a notice when iTunes rate-limits.
4. Read the summary and the report, then confirm to apply. The default answer is **no**.

Non-interactive (no questions, report only unless `--apply`):

```powershell
python -m toolkit.audio.album_fixer --folder "D:\Music" [--full] [--apply clean|all]
python -m toolkit.audio.album_fixer --restore reports\album_fix_backup_<time>.json
```

`--apply clean` writes only the safest rows (plain iTunes matches); `--apply all` writes every CHANGE row.

`--offline` is a dry run from the local cache only: no network, nothing written except the report, finishes in
seconds. Songs that were never looked up show as `NOT_FOUND` with the note `not in cache (offline dry run)`.
It cannot be combined with `--apply`.

---

## Report: `reports/album_fix_report.tsv`

| Status | Meaning | Applied? |
|--------|---------|----------|
| `CHANGE` | Current album looks like a compilation/playlist (or is shared by several artists) and an original album was found | yes |
| `REVIEW` | Albums differ but the current one looks legit, or confidence is low (soundtracks, reissues) | no |
| `NOT_FOUND` | No source found the song | no |
| `OK` | Already correct, or skipped in fast mode because the album looks fine | no |

The `source` and `note` columns say which source was used and why a fallback was needed. Check the
MusicBrainz and Genius rows first; they are the least certain. Songs that were first released as a single can
legitimately resolve to the album that later included them, or stay a single/EP.

---

## Safety

- **Backup:** before writing, the current album, year and track/disc tags of every file that will change are saved to
  `reports/album_fix_backup_<time>.json`. `--restore` puts them back.
- **Cover art is not backed up.** The old cover cannot be restored.
- Track and disc numbers are replaced with the original album's numbers; implausible ones (iTunes sometimes returns
  138 of 163) are rejected. When the number is unknown, the old one (which belonged to the compilation) is removed.
- The year is only written when the file has none.

## Speed and cache

iTunes allows about 20 requests per minute, so a new song takes about 3 seconds (MusicBrainz: 1 per second).
Results are cached in `.cache/album_resolver_cache.json` every 20 songs, so an interrupted run resumes where it
stopped and a re-run is almost instant. Delete that file to force fresh lookups.

## Related fixes

Tagger mode 1 now replaces a compilation album tag instead of protecting it, and the Album Art Fixer (menu 6) no
longer favors covers that match a compilation album and only considers results for the same song.
