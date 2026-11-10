"""Album & cover fixer: replace compilation/playlist album tags with the original studio album and its cover."""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from mutagen import MutagenError
from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError, TALB, TDRC, TPOS, TRCK
from mutagen.mp4 import MP4
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table

from toolkit.audio import album_resolver
from toolkit.audio.album_resolver import (
    is_compilation_name,
    normalize,
    primary_artist,
    resolve_album,
    save_cache,
    strip_edition,
)
from toolkit.audio.artwork.embed import embed_artwork
from toolkit.audio.artwork.sources import fetch_artwork_bytes
from toolkit.audio.metadata import read_audio_metadata
from toolkit.core import AUDIO_LIBRARY_DIR, REPORTS_DIR
from toolkit.core.constants import DEFAULT_MAX_WORKERS
from toolkit.core.logging import get_logger

console = Console()
logger = get_logger(__name__)

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".flac")
REPORT_NAME = "album_fix_report.tsv"
REPORT_COLUMNS = [
    "status",
    "file",
    "artist",
    "title",
    "current_album",
    "new_album",
    "year",
    "track",
    "source",
    "score",
    "note",
    "art_url",
]

STATUS_OK = "OK"
STATUS_CHANGE = "CHANGE"
STATUS_REVIEW = "REVIEW"
STATUS_NOT_FOUND = "NOT_FOUND"


def find_audio_files(folder: str) -> list[str]:
    """All audio files under folder, including subfolders."""
    found = []
    for root, _dirs, files in os.walk(folder):
        found.extend(os.path.join(root, f) for f in files if f.lower().endswith(AUDIO_EXTENSIONS))
    return sorted(found)


def shared_album_names(entries: list[dict[str, Any]]) -> set[str]:
    """Normalized album names used by two or more different primary artists (almost always a compilation)."""
    artists_by_album: dict[str, set[str]] = defaultdict(set)
    for e in entries:
        if e["album"]:
            artists_by_album[normalize(e["album"])].add(normalize(primary_artist(e["artist"])))
    return {album for album, artists in artists_by_album.items() if len(artists) >= 2}


def decide(entry: dict[str, Any], resolved: Optional[dict[str, Any]], shared: set[str]) -> dict[str, Any]:
    """Build one report row for a file from its current tags and the resolver result."""
    row = {
        "status": STATUS_NOT_FOUND,
        "file": entry["path"],
        "artist": entry["artist"],
        "title": entry["title"],
        "current_album": entry["album"],
        "new_album": "",
        "year": "",
        "track": "",
        "source": "",
        "score": "",
        "note": "",
        "art_url": "",
    }
    if not resolved or not resolved.get("album"):
        return row

    row.update(
        new_album=resolved["album"],
        year=resolved.get("year", ""),
        source=resolved["source"],
        score="" if resolved.get("score") is None else resolved["score"],
        note=resolved.get("note", ""),
        art_url=resolved.get("art_url", ""),
        track=f"{resolved['track']}/{resolved['track_total']}" if resolved.get("track") else "",
        track_no=resolved.get("track", 0),
        track_total=resolved.get("track_total", 0),
        disc_no=resolved.get("disc", 0),
        disc_total=resolved.get("disc_total", 0),
    )
    current = entry["album"]
    if current and strip_edition(current) == strip_edition(resolved["album"]):
        row["status"] = STATUS_OK
        row["new_album"] = current
        row["art_url"] = ""
        return row

    suspicious = (not current) or normalize(current) in shared or is_compilation_name(current, entry["artist"])
    low_confidence = bool(resolved.get("uncertain"))
    row["status"] = STATUS_CHANGE if suspicious and not low_confidence else STATUS_REVIEW
    return row


def plan_folder(
    folder: str,
    on_row: Optional[Callable[[dict[str, Any], int, int], None]] = None,
    on_start: Optional[Callable[[dict[str, Any], int, int], None]] = None,
    only_suspicious: bool = False,
) -> list[dict[str, Any]]:
    """Read tags of every file, look up the original album, return one report row per file.

    With only_suspicious, files whose album neither looks like a compilation nor is shared by several artists are
    not looked up at all (marked OK), which skips most of the slow rate-limited requests.
    """
    entries = []
    for path in find_audio_files(folder):
        meta = read_audio_metadata(path)
        entries.append(
            {
                "path": path,
                "title": meta.title or "",
                "artist": meta.artist or "",
                "album": meta.album or "",
                "year": meta.year or "",
            }
        )
    shared = shared_album_names(entries)

    rows = []
    total = len(entries)
    for index, entry in enumerate(entries, 1):
        resolved = None
        if (
            only_suspicious
            and entry["album"]
            and not (normalize(entry["album"]) in shared or is_compilation_name(entry["album"], entry["artist"]))
        ):
            row = decide(entry, None, shared)
            row.update(status=STATUS_OK, note="skipped lookup: album looks fine")
            rows.append(row)
            if on_row:
                on_row(row, index, total)
            continue
        if on_start:
            on_start(entry, index, total)
        if entry["title"] and entry["artist"]:
            resolved = resolve_album(entry["artist"], entry["title"], str(entry["year"])[:4])
        row = decide(entry, resolved, shared)
        rows.append(row)
        if on_row:
            on_row(row, index, total)
    save_cache()
    return rows


def write_report(rows: list[dict[str, Any]], report_dir: str = REPORTS_DIR) -> str:
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, REPORT_NAME)
    order = {STATUS_CHANGE: 0, STATUS_REVIEW: 1, STATUS_NOT_FOUND: 2, STATUS_OK: 3}
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_COLUMNS, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (order[r["status"]], r["artist"].lower(), r["title"].lower())):
            writer.writerow(row)
    return path


def write_album_tag(file_path: str, album: str, year: str = "", position: Optional[dict[str, int]] = None) -> bool:
    """Set the album tag (year only when the file has none) and the track/disc position.

    The old track/disc numbers belonged to the previous (compilation) album, so they are replaced with the
    original album's numbers, or removed when those are unknown. Title and artist are left untouched.
    """
    pos = position or {}
    track, track_total = pos.get("track", 0), pos.get("track_total", 0)
    disc, disc_total = pos.get("disc", 0), pos.get("disc_total", 0)
    low = file_path.lower()
    try:
        if low.endswith(".m4a"):
            audio = MP4(file_path)
            audio["©alb"] = album
            if year and not audio.get("©day"):
                audio["©day"] = year
            audio.pop("trkn", None)
            audio.pop("disk", None)
            if track:
                audio["trkn"] = [(track, track_total)]
            if disc:
                audio["disk"] = [(disc, disc_total)]
            audio.save()
        elif low.endswith(".mp3"):
            try:
                tags = ID3(file_path)
            except ID3NoHeaderError:
                tags = ID3()
            tags.add(TALB(encoding=3, text=album))
            if year and not tags.get("TDRC"):
                tags.add(TDRC(encoding=3, text=year))
            tags.delall("TRCK")
            tags.delall("TPOS")
            if track:
                tags.add(TRCK(encoding=3, text=f"{track}/{track_total}"))
            if disc:
                tags.add(TPOS(encoding=3, text=f"{disc}/{disc_total}"))
            tags.save(file_path, v2_version=3)
        elif low.endswith(".flac"):
            audio = FLAC(file_path)
            audio["album"] = album
            if year and not audio.get("date"):
                audio["date"] = year
            for key in ("tracknumber", "tracktotal", "totaltracks", "discnumber", "disctotal", "totaldiscs"):
                audio.pop(key, None)
            if track:
                audio["tracknumber"] = str(track)
                audio["tracktotal"] = str(track_total)
            if disc:
                audio["discnumber"] = str(disc)
                audio["disctotal"] = str(disc_total)
            audio.save()
        else:
            return False
        return True
    except (MutagenError, OSError, KeyError, TypeError) as e:
        logger.warning(f"Failed writing album tag {file_path}: {e}")
        return False


def apply_row(row: dict[str, Any]) -> dict[str, Any]:
    """Write the new album tag and cover for one report row."""
    position = {
        "track": row.get("track_no", 0),
        "track_total": row.get("track_total", 0),
        "disc": row.get("disc_no", 0),
        "disc_total": row.get("disc_total", 0),
    }
    ok = write_album_tag(row["file"], row["new_album"], str(row["year"]), position)
    cover = False
    if ok and row["art_url"]:
        img = fetch_artwork_bytes(row["art_url"])
        cover = bool(img) and embed_artwork(row["file"], img)
    return {"file": row["file"], "tag": ok, "cover": cover}


def is_clean_change(row: dict[str, Any]) -> bool:
    """CHANGE rows with the highest confidence: a plain iTunes match, no fallback or warning note."""
    return row["status"] == STATUS_CHANGE and row["source"] == "iTunes" and not row["note"]


def _pair(value: Any) -> list[int]:
    """'7/15', (7, 15) or '7' -> [7, 15]; anything unusable -> [0, 0]."""
    try:
        if isinstance(value, (tuple, list)):
            return [int(value[0] or 0), int(value[1] or 0)]
        number, _, total = str(value).partition("/")
        return [int(number), int(total or 0)]
    except (ValueError, TypeError, IndexError):
        return [0, 0]


def snapshot_tags(file_path: str) -> dict[str, Any]:
    """Current album, year and track/disc position of a file (cover art is not included)."""
    low = file_path.lower()
    snap: dict[str, Any] = {"file": file_path, "album": "", "year": "", "track": [0, 0], "disc": [0, 0]}
    try:
        if low.endswith(".m4a"):
            tags = MP4(file_path)
            snap["album"] = (tags.get("\xa9alb") or [""])[0]
            snap["year"] = (tags.get("\xa9day") or [""])[0]
            snap["track"] = _pair((tags.get("trkn") or [(0, 0)])[0])
            snap["disc"] = _pair((tags.get("disk") or [(0, 0)])[0])
        elif low.endswith(".mp3"):
            tags = ID3(file_path)
            snap["album"] = str(tags.get("TALB", ""))
            snap["year"] = str(tags.get("TDRC", ""))
            snap["track"] = _pair(str(tags.get("TRCK", "")))
            snap["disc"] = _pair(str(tags.get("TPOS", "")))
        elif low.endswith(".flac"):
            tags = FLAC(file_path)
            snap["album"] = (tags.get("album") or [""])[0]
            snap["year"] = (tags.get("date") or [""])[0]
            snap["track"] = [_pair(tags.get("tracknumber", ["0"])[0])[0], _pair(tags.get("tracktotal", ["0"])[0])[0]]
            snap["disc"] = [_pair(tags.get("discnumber", ["0"])[0])[0], _pair(tags.get("disctotal", ["0"])[0])[0]]
    except (MutagenError, OSError) as e:
        logger.warning(f"Could not snapshot tags of {file_path}: {e}")
    return snap


def backup_tags(rows: list[dict[str, Any]], report_dir: str = REPORTS_DIR) -> str:
    """Save the current album/year/track tags of the files about to change, so they can be restored."""
    import datetime
    import json

    os.makedirs(report_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(report_dir, f"album_fix_backup_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump([snapshot_tags(r["file"]) for r in rows], f, ensure_ascii=False, indent=1)
    return path


def restore_backup(backup_path: str) -> tuple[int, int]:
    """Put the album and track/disc tags back from a backup file. Returns (restored, total).

    Cover art is not part of the backup and stays as it is.
    """
    import json

    with open(backup_path, "r", encoding="utf-8") as f:
        entries = json.load(f)
    restored = 0
    for e in entries:
        position = {
            "track": e["track"][0],
            "track_total": e["track"][1],
            "disc": e["disc"][0],
            "disc_total": e["disc"][1],
        }
        if write_album_tag(e["file"], e["album"], "", position):
            restored += 1
    return restored, len(entries)


def apply_rows(rows: list[dict[str, Any]], max_workers: int = DEFAULT_MAX_WORKERS) -> list[dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(apply_row, rows))


def _summary_table(rows: list[dict[str, Any]]) -> Table:
    counts = defaultdict(int)
    for r in rows:
        counts[r["status"]] += 1
    table = Table(title="Album fix plan", header_style="bold cyan")
    table.add_column("Status")
    table.add_column("Files", justify="right")
    table.add_column("Meaning")
    meaning = {
        STATUS_CHANGE: "compilation/playlist album, original album found",
        STATUS_REVIEW: "album differs but current one looks legit, or low confidence",
        STATUS_NOT_FOUND: "no match on iTunes or MusicBrainz",
        STATUS_OK: "already correct",
    }
    for status in (STATUS_CHANGE, STATUS_REVIEW, STATUS_NOT_FOUND, STATUS_OK):
        table.add_row(status, str(counts[status]), meaning[status])
    return table


def main() -> None:
    console.clear()
    console.print(
        Panel(
            "[bold cyan]ALBUM & COVER FIXER[/bold cyan]\n"
            "Replaces compilation / playlist album tags with the original studio album and its cover.\n"
            "[dim]iTunes first; MusicBrainz when the iTunes score is below 70. "
            "Writes a report first, files change only after you confirm.[/dim]",
            border_style="green",
        )
    )
    folder = Prompt.ask("\nFolder to scan (subfolders included)", default=AUDIO_LIBRARY_DIR).strip().strip('"')
    if not os.path.isdir(folder):
        console.print(f"[bold red]Folder not found:[/bold red] {folder}")
        return
    total = len(find_audio_files(folder))
    if not total:
        console.print("[yellow]No audio files found.[/yellow]")
        return
    only_suspicious = Confirm.ask(
        "Only look up songs whose album looks like a compilation/playlist? (much faster, ~half the time)",
        default=True,
    )
    console.print(
        f"[green]{total} audio file(s). Lookups are rate limited (about 3 s per new song); "
        "results are cached every 20 songs, so you can stop and resume.[/green]"
    )

    colors = {STATUS_CHANGE: "green", STATUS_REVIEW: "yellow", STATUS_NOT_FOUND: "red", STATUS_OK: "dim"}
    counts: dict[str, int] = defaultdict(int)
    progress = Progress(
        SpinnerColumn(),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        TextColumn("[cyan]{task.fields[now]}[/cyan]"),
        console=console,
    )
    task = progress.add_task("lookup", total=total, now="starting...")
    current = {"song": ""}

    def on_start(entry: dict[str, Any], index: int, count: int) -> None:
        current["song"] = f"{entry['artist']} - {entry['title']}"
        progress.update(task, now=f"{current['song'][:50]}: searching")

    def on_row(row: dict[str, Any], index: int, count: int) -> None:
        counts[row["status"]] += 1
        progress.advance(task)
        if row["note"].startswith("skipped"):
            return
        arrow = f"{row['current_album'] or '(none)'} -> {row['new_album'] or '?'}"
        via = f" [{row['source']}]" if row["source"] else ""
        color = colors[row["status"]]
        progress.console.print(
            f"[dim]{index}/{count}[/dim] [{color}]{row['status']:<9}[/{color}] "
            f"{row['artist']} - {row['title']} | {arrow}{via}"
        )
        progress.update(
            task,
            now=f"CHANGE {counts[STATUS_CHANGE]} | REVIEW {counts[STATUS_REVIEW]} | "
            f"NOT_FOUND {counts[STATUS_NOT_FOUND]}",
        )

    album_resolver.status_hook = lambda msg: progress.update(task, now=f"{current['song'][:50]}: {msg}")
    try:
        with progress:
            rows = plan_folder(folder, on_row=on_row, on_start=on_start, only_suspicious=only_suspicious)
    finally:
        album_resolver.status_hook = None

    report = write_report(rows)
    console.print(_summary_table(rows))
    console.print(f"[bold green]Report:[/bold green] {report}")

    changes = [r for r in rows if r["status"] == STATUS_CHANGE]
    if not changes:
        return
    if not Confirm.ask(f"\nApply {len(changes)} CHANGE row(s) (album tag + cover)?", default=False):
        console.print("[dim]Nothing changed.[/dim]")
        return
    console.print(f"[dim]Backup of current tags: {backup_tags(changes)}[/dim]")
    results = apply_rows(changes)
    console.print(
        Panel(
            f"Album tag written: {sum(r['tag'] for r in results)}/{len(results)}  |  "
            f"Cover embedded: {sum(r['cover'] for r in results)}/{len(results)}",
            title="Done",
            border_style="green",
        )
    )


def run_cli(argv: Optional[list[str]] = None) -> int:
    """Non-interactive mode: plain progress lines, writes the report, applies only with --apply."""
    import argparse
    import time

    parser = argparse.ArgumentParser(description="Album & cover fixer (report only unless --apply)")
    parser.add_argument("--folder", default=AUDIO_LIBRARY_DIR, help="folder to scan (subfolders included)")
    parser.add_argument("--full", action="store_true", help="look up every song, not only suspicious albums")
    parser.add_argument(
        "--apply",
        nargs="?",
        const="all",
        choices=["clean", "all"],
        help="write CHANGE rows after the report: 'clean' = plain iTunes matches only, 'all' = every CHANGE",
    )
    parser.add_argument("--restore", metavar="BACKUP_JSON", help="restore album/track tags from a backup and exit")
    args = parser.parse_args(argv)

    if args.restore:
        restored, count = restore_backup(args.restore)
        print(f"Restored {restored}/{count} file(s) from {args.restore}", flush=True)
        return 0
    if not os.path.isdir(args.folder):
        print(f"Folder not found: {args.folder}", flush=True)
        return 1
    total = len(find_audio_files(args.folder))
    print(f"Scanning {total} file(s) in {args.folder} ({'full' if args.full else 'fast'} mode)", flush=True)
    started = time.monotonic()
    counts: dict[str, int] = defaultdict(int)
    looked_up = {"n": 0}

    def on_row(row: dict[str, Any], index: int, count: int) -> None:
        counts[row["status"]] += 1
        if row["note"].startswith("skipped"):
            return
        looked_up["n"] += 1
        arrow = f"{row['current_album'] or '(none)'} -> {row['new_album'] or '?'}"
        via = f" [{row['source']}]" if row["source"] else ""
        print(f"{index}/{count} {row['status']:<9} {row['artist']} - {row['title']} | {arrow}{via}", flush=True)
        if looked_up["n"] % 25 == 0:
            elapsed = time.monotonic() - started
            eta = elapsed / index * (count - index)
            print(
                f"--- {index}/{count} done | CHANGE {counts[STATUS_CHANGE]} REVIEW {counts[STATUS_REVIEW]} "
                f"NOT_FOUND {counts[STATUS_NOT_FOUND]} | elapsed {elapsed / 60:.0f} min, ~{eta / 60:.0f} min left",
                flush=True,
            )

    album_resolver.status_hook = lambda msg: print(f"    ({msg})", flush=True) if "rate limit" in msg else None
    try:
        rows = plan_folder(args.folder, on_row=on_row, only_suspicious=not args.full)
    finally:
        album_resolver.status_hook = None
    report = write_report(rows)
    print(
        f"DONE in {(time.monotonic() - started) / 60:.1f} min | "
        + " | ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        + f"\nReport: {report}",
        flush=True,
    )
    if args.apply:
        chosen = [r for r in rows if (is_clean_change(r) if args.apply == "clean" else r["status"] == STATUS_CHANGE)]
        print(f"Applying {len(chosen)} row(s) ({args.apply})...", flush=True)
        print(f"Backup of current tags: {backup_tags(chosen)}", flush=True)
        results = apply_rows(chosen)
        failed = [r["file"] for r in results if not r["tag"] or not r["cover"]]
        for path in failed:
            print(f"  not fully applied: {path}", flush=True)
        print(
            f"Applied: tag {sum(r['tag'] for r in results)}/{len(results)}, "
            f"cover {sum(r['cover'] for r in results)}/{len(results)}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        raise SystemExit(run_cli())
    main()
