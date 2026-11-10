"""Resolve the original studio album for a track: iTunes first, MusicBrainz when iTunes scores poorly."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import unicodedata
from typing import Any, Callable, Optional

from toolkit.core import CACHE_DIR, http_get, http_post
from toolkit.core.logging import get_logger
from toolkit.playlists.parser import COMPILATION_KEYWORDS

logger = get_logger(__name__)

SCORE_THRESHOLD = 70
ITUNES_MIN_INTERVAL = 3.0  # iTunes Search API starts returning 403 above ~20 requests/minute
MUSICBRAINZ_MIN_INTERVAL = 1.1  # MusicBrainz allows 1 request/second
MB_USER_AGENT = "spotify-apple-music-toolkit/1.0"
CACHE_FILE = os.path.join(CACHE_DIR, "album_resolver_cache.json")

PENALTY_COMPILATION = 60
PENALTY_LIVE = 50
PENALTY_SINGLE_EP = 15
PENALTY_EDITION = 5
BONUS_YEAR_MATCH = 10
BONUS_FULL_TITLE = 20

_COMPILATION_RE = re.compile(
    r"hits|best of|greatest|superhits|essential|collection|playlist|anthems|classics|ballads|songs|karaoke|"
    r"covers|udiscover|workout|party|summer|nostalgia|vol\.|volume|vibes|soundtrack|motion picture|"
    r"original cast|broadway|sing along|tribute|\b\d{2,4}s\b|bonus tracks|\(the album\)|bangers|throwback|"
    r"\bsingles\b|remix album|anthology|the very best|top \d+|now that|"
    r"m[uú]sicas|canciones|[eé]xitos|hinos|essenciais|tesoros|sucessos|cl[aá]ssicos|"
    r"[a-zÀ-ɏ]{3,} (19|20)\d{2}( ?/ ?\d+)?$",
    re.IGNORECASE,
)
_BEST_OF_RE = re.compile(
    r"greatest|best of|\bhits\b|collection|essential|\bsingles\b|remix album|anthology|the very best|the best",
    re.IGNORECASE,
)
_VERSION_RE = re.compile(
    r"\blive\b|demo|session|acoustic|karaoke|instrumental|sped|slowed|remix|stripped|unplugged|version|"
    r"\bmix\b|\bedit\b",
    re.IGNORECASE,
)
_REISSUE_RE = re.compile(r"anniversary|deluxe|remaster|expanded|\b[XVI]{2,}\b|edition", re.IGNORECASE)
_EDITION_RE = re.compile(r"deluxe|edition|expanded|remaster", re.IGNORECASE)
_SINGLE_EP_RE = re.compile(r"-\s*(single|ep)\s*$", re.IGNORECASE)
_SPLIT_ARTIST_RE = re.compile(r"\s*(?:&|,|/|\bfeat\.?|\bft\.?|\bfeaturing\b|\bwith\b|\bx\b)\s*", re.IGNORECASE)

status_hook: Optional[Callable[[str], None]] = None  # live progress messages for the UI (optional)
_rate_lock = threading.Lock()
_last_call: dict[str, float] = {}
_cache: dict[str, Any] = {}
_cache_loaded = False
_unsaved = 0
SAVE_EVERY = 20  # persist the cache regularly so an interrupted run can resume


def normalize(text: str) -> str:
    """Lowercase ASCII alphanumerics only, for tolerant comparison."""
    folded = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", folded.replace("&", "and"))


def base_title(title: str) -> str:
    """Normalized title without (...), [...] and ' - suffix' parts."""
    return normalize(re.sub(r"\s*[\(\[].*?[\)\]]|\s+-\s+.*$", "", title or ""))


def primary_artist(artist: str) -> str:
    return _SPLIT_ARTIST_RE.split(artist or "", maxsplit=1)[0].strip()


def wants_version(title: str) -> bool:
    """True when the title itself names a live/remix/acoustic/etc. version."""
    return bool(_VERSION_RE.search(title or ""))


def is_compilation_name(album: str, artist: str = "") -> bool:
    """True when an album name looks like a compilation, playlist or soundtrack rather than the artist's album."""
    if not album:
        return False
    low = album.lower()
    artist_norm = normalize(primary_artist(artist))
    if artist_norm and artist_norm in normalize(album) and not _BEST_OF_RE.search(album):
        return False  # "The Essential 311" style, titled after the artist
    if any(k in low for k in COMPILATION_KEYWORDS):
        return True
    return bool(_COMPILATION_RE.search(album))


def strip_edition(album: str) -> str:
    """Normalized album name without (Deluxe ...) / [...] / '- Single' parts."""
    cleaned = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", album or "")
    cleaned = _SINGLE_EP_RE.sub("", cleaned)
    return normalize(cleaned)


def score_itunes_item(item: dict[str, Any], artist: str, title: str, year: str = "") -> Optional[tuple[int, list[str]]]:
    """Score one iTunes song result. None when it is not the same song by the same artist."""
    if normalize(primary_artist(artist)) not in normalize(item.get("artistName", "")):
        return None
    if base_title(item.get("trackName", "")) != base_title(title):
        return None

    album = item.get("collectionName", "")
    track_name = item.get("trackName", "")
    version_wanted = wants_version(title)
    score, why = 100, []

    various = (item.get("collectionArtistName") or "").lower().startswith("various")
    if various or is_compilation_name(album, artist):
        score -= PENALTY_COMPILATION
        why.append("compilation/soundtrack")
    if not version_wanted and (_VERSION_RE.search(track_name) or _VERSION_RE.search(album)):
        score -= PENALTY_LIVE
        why.append("live/demo/version")
    if _SINGLE_EP_RE.search(album):
        score -= PENALTY_SINGLE_EP
        why.append("single/EP")
    if _EDITION_RE.search(album):
        score -= PENALTY_EDITION
    if year and str(item.get("releaseDate", ""))[:4] == str(year):
        score += BONUS_YEAR_MATCH
    if version_wanted and normalize(track_name) == normalize(title):
        score += BONUS_FULL_TITLE
    return score, why


MAX_ALBUM_TRACKS = 60


def valid_track_info(number: Any, total: Any, disc: Any = None, discs: Any = None) -> dict[str, int]:
    """Track/disc numbers only when they are plausible (iTunes sometimes returns 138 of 163 for bundles)."""
    try:
        n, t = int(number), int(total)
    except (TypeError, ValueError):
        return {}
    if not 1 <= n <= t <= MAX_ALBUM_TRACKS:
        return {}
    info = {"track": n, "track_total": t}
    try:
        d, ds = int(disc or 1), int(discs or 1)
        if 1 <= d <= ds <= 3:  # box sets list each album as "disc 3 of 6"; that is not the album's own disc
            info.update(disc=d, disc_total=ds)
    except (TypeError, ValueError):
        pass
    return info


def _item_track(item: dict[str, Any]) -> dict[str, int]:
    return valid_track_info(
        item.get("trackNumber"), item.get("trackCount"), item.get("discNumber"), item.get("discCount")
    )


def choose_itunes(results: list[dict[str, Any]], artist: str, title: str, year: str = "") -> Optional[dict[str, Any]]:
    """Pick the best iTunes candidate: highest score, then earliest release."""
    ranked = []
    for item in results:
        scored = score_itunes_item(item, artist, title, year)
        if scored:
            ranked.append((-scored[0], str(item.get("releaseDate", "9999")), item, scored[1]))
    if not ranked:
        return None
    # equal score: prefer the plain album (fewest tracks, not a bundle) then the earliest release
    ranked.sort(key=lambda r: (r[0], r[2].get("trackCount") or 9999, r[2].get("discCount") or 1, r[1]))
    neg_score, date, item, why = ranked[0]
    art = (item.get("artworkUrl100") or "").replace("100x100bb", "1000x1000bb")
    track = _item_track(item)
    if not track:  # best entry is a bundle: borrow the position from another edition of the same album
        same_album = strip_edition(item.get("collectionName", ""))
        for _neg, _date, other, _why in ranked:
            if strip_edition(other.get("collectionName", "")) == same_album and _item_track(other):
                track = _item_track(other)
                break
    return {
        **track,
        "source": "iTunes",
        "score": -neg_score,
        "album": item.get("collectionName", ""),
        "year": date[:4],
        "art_url": art,
        "why": why,
    }


def choose_musicbrainz(recordings: list[dict[str, Any]], title: str = "") -> Optional[dict[str, Any]]:
    """Pick the earliest official plain studio album (no live/compilation/soundtrack secondary type).

    With title, only recordings of that song are used. Reissue-looking albums (XXV, Anniversary, Deluxe)
    rank after plain ones and mark the result as uncertain.
    """
    if title:
        exact = [r for r in recordings if normalize(r.get("title", "")) == normalize(title)]
        wanted = base_title(title)
        same_song = exact or [r for r in recordings if base_title(r.get("title", "")) == wanted]
        recordings = same_song or recordings
    candidates = []
    for rec in recordings:
        for rel in rec.get("releases", []):
            group = rel.get("release-group", {})
            if group.get("primary-type") != "Album" or group.get("secondary-types"):
                continue
            if rel.get("status") != "Official":
                continue
            name = rel.get("title", "")
            if is_compilation_name(name):
                continue
            candidates.append(
                (bool(_REISSUE_RE.search(name)), rel.get("date") or "9999", name, group.get("id", ""), rel)
            )
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[:4])
    reissue, date, album, group_id, release = candidates[0]
    art = f"https://coverartarchive.org/release-group/{group_id}/front-1200" if group_id else ""
    result = {
        "source": "MusicBrainz",
        "score": None,
        "album": album,
        "year": date[:4],
        "art_url": art,
        "why": [],
        **_musicbrainz_track(release),
    }
    if reissue:
        result["uncertain"] = True
        result["note"] = "only a reissue/anniversary edition found on MusicBrainz, verify the original album"
    return result


def _say(message: str) -> None:
    if status_hook:
        status_hook(message)


def _throttle(key: str, interval: float) -> None:
    with _rate_lock:
        wait = _last_call.get(key, 0.0) + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[key] = time.monotonic()


def search_itunes(artist: str, title: str, year: str = "") -> Optional[dict[str, Any]]:
    clean_title = re.sub(r"\s*[\(\[].*?[\)\]]", "", title).strip()
    term = f"{primary_artist(artist)} {clean_title}"
    params = {"term": term, "entity": "song", "limit": 50, "country": "US"}
    for attempt in range(3):
        _throttle("itunes", ITUNES_MIN_INTERVAL)
        try:
            res = http_get("https://itunes.apple.com/search", params=params)
        except OSError as e:
            logger.warning(f"iTunes request failed for '{term}': {e}")
            return None
        if res.status_code == 200:
            return choose_itunes(res.json().get("results", []), artist, title, year)
        if res.status_code in (403, 429):
            wait = 30 * (attempt + 1)
            _say(f"iTunes rate limit hit, waiting {wait}s (retry {attempt + 1}/3)")
            time.sleep(wait)
            continue
        return None
    return None


def _musicbrainz_track(release: dict[str, Any]) -> dict[str, int]:
    """Track/disc position from a MusicBrainz search release, when the result includes media."""
    try:
        media = release["media"]
        disc_no = int(media[0].get("position", 1))
        number = int(media[0]["track"][0]["number"])
        total = sum(int(m.get("track-count", 0)) for m in media) if len(media) == 1 else int(media[0]["track-count"])
        return valid_track_info(number, total, disc_no, len(media))
    except (KeyError, IndexError, TypeError, ValueError):
        return {}


_FEAT_PAREN_RE = re.compile(r"\s*[\(\[]\s*(?:feat|ft|with|from|prod)\b.*?[\)\]]", re.IGNORECASE)


def _musicbrainz_query(artist: str, song: str) -> Optional[list[dict[str, Any]]]:
    clean_song = song.replace('"', "").strip()
    clean_artist = primary_artist(artist).replace('"', "")
    _throttle("musicbrainz", MUSICBRAINZ_MIN_INTERVAL)
    try:
        res = http_get(
            "https://musicbrainz.org/ws/2/recording",
            params={"query": f'recording:"{clean_song}" AND artist:"{clean_artist}"', "fmt": "json", "limit": 25},
            headers={"User-Agent": MB_USER_AGENT},
        )
    except OSError as e:
        logger.warning(f"MusicBrainz request failed for '{clean_song}': {e}")
        return None
    if res.status_code != 200:
        return None
    return res.json().get("recordings", [])


def search_musicbrainz(artist: str, title: str) -> Optional[dict[str, Any]]:
    """Search with the full title first (keeps "(Time of Your Life)"), then without any (...) part."""
    full = _FEAT_PAREN_RE.sub("", title).strip()
    stripped = re.sub(r"\s*[\(\[].*?[\)\]]", "", title).strip()
    for query_title in dict.fromkeys([full, stripped]):
        recordings = _musicbrainz_query(artist, query_title)
        best = choose_musicbrainz(recordings or [], title)
        if best:
            return best
    return None


GENIUS_API = "https://api.genius.com"
_genius_token: list[str] = []  # bearer token, fetched once per run


def _genius_headers() -> Optional[dict[str, str]]:
    """Bearer header from GENIUS_CLIENT_ID / GENIUS_CLIENT_SECRET (.env), or None when not configured."""
    client_id, client_secret = os.getenv("GENIUS_CLIENT_ID"), os.getenv("GENIUS_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    if not _genius_token:
        try:
            res = http_post(
                f"{GENIUS_API}/oauth/token",
                json={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
            )
            token = res.json().get("access_token") if res.status_code == 200 else None
        except (OSError, ValueError) as e:
            logger.warning(f"Genius token request failed: {e}")
            return None
        if not token:
            logger.warning("Genius rejected the client credentials; check GENIUS_CLIENT_ID/GENIUS_CLIENT_SECRET")
            return None
        _genius_token.append(token)
    return {"Authorization": f"Bearer {_genius_token[0]}"}


def _genius_year(info: dict[str, Any]) -> str:
    """Release year from a Genius song: release_date, else the display date, else the album's date."""
    for value in (info.get("release_date"), info.get("release_date_for_display")):
        match = re.search(r"(19|20)\d{2}", str(value or ""))
        if match:
            return match.group(0)
    components = (info.get("album") or {}).get("release_date_components") or {}
    return str(components.get("year") or "")


def search_genius(artist: str, title: str) -> Optional[dict[str, Any]]:
    """Album Genius lists for the song (first matching search hit that has an album)."""
    headers = _genius_headers()
    if not headers:
        return None
    artist_key, wanted = normalize(primary_artist(artist)), base_title(title)
    try:
        _throttle("genius", 0.5)
        found = http_get(f"{GENIUS_API}/search", params={"q": f"{primary_artist(artist)} {title}"}, headers=headers)
        hits = found.json().get("response", {}).get("hits", []) if found.status_code == 200 else []
        for hit in hits:
            song = hit.get("result", {})
            if artist_key not in normalize(song.get("primary_artist", {}).get("name", "")):
                continue
            if base_title(song.get("title", "")) != wanted:
                continue
            if not wants_version(title) and wants_version(song.get("title", "")):
                continue
            _throttle("genius", 0.5)
            detail = http_get(f"{GENIUS_API}/songs/{song['id']}", headers=headers)
            info = detail.json().get("response", {}).get("song", {}) if detail.status_code == 200 else {}
            album = info.get("album") or {}
            if not album.get("name"):
                continue
            result = {
                "source": "Genius",
                "score": None,
                "album": album["name"],
                "year": _genius_year(info),
                "art_url": album.get("cover_art_url") or "",
                "why": [],
            }
            if is_compilation_name(album["name"], artist):
                result["uncertain"] = True
            return result
    except (OSError, ValueError, KeyError) as e:
        logger.warning(f"Genius lookup failed for '{artist} - {title}': {e}")
    return None


def _load_cache() -> None:
    global _cache_loaded, _cache
    if _cache_loaded:
        return
    _cache_loaded = True
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _cache = data
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed loading album resolver cache: {e}")


def save_cache() -> None:
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)
    except OSError as e:
        logger.warning(f"Failed saving album resolver cache: {e}")


def resolve_album(artist: str, title: str, year: str = "") -> Optional[dict[str, Any]]:
    """Original-album lookup. iTunes when score >= SCORE_THRESHOLD, otherwise MusicBrainz."""
    _load_cache()
    key = f"{normalize(artist)}|{normalize(title)}|{year}"
    if key in _cache:
        _say("cached result")
        return _cache[key]

    _say("searching iTunes")
    itunes = search_itunes(artist, title, year)
    single_only = bool(itunes) and "single/EP" in itunes["why"]
    if itunes and itunes["score"] >= SCORE_THRESHOLD and not single_only:
        result: Optional[dict[str, Any]] = itunes
    else:
        if single_only:
            reason = "iTunes only had a single/EP"
        else:
            reason = f"iTunes score {itunes['score']}" if itunes else "not found on iTunes"
        _say(f"{reason}, trying MusicBrainz")
        mb = search_musicbrainz(artist, title)
        genius = None
        if mb is None or mb.get("uncertain"):
            _say("trying Genius")
            genius = search_genius(artist, title)
        if genius:
            genius["note"] = f"{reason}, MusicBrainz {'unsure' if mb else 'found nothing'}, used Genius"
            result = genius
        elif mb:
            note = f"{reason}, used MusicBrainz"
            mb["note"] = f"{note}; {mb['note']}" if mb.get("note") else note
            result = mb
        elif itunes and single_only:
            itunes["note"] = "no studio album found on MusicBrainz, kept the iTunes single/EP"
            result = itunes
        elif itunes:
            itunes["note"] = "low iTunes score and not found on MusicBrainz"
            itunes["uncertain"] = True
            result = itunes
        else:
            result = None

    global _unsaved
    _cache[key] = result
    _unsaved += 1
    if _unsaved >= SAVE_EVERY:
        _unsaved = 0
        save_cache()
    return result
