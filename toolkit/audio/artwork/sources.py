"""Artwork search sources (iTunes, Deezer) and quality scoring."""
from __future__ import annotations

import os
import random
import re
from typing import Optional

from toolkit.core import http_get
from toolkit.core.constants import (
    ITUNES_ARTWORK_FALLBACK_SIZES,
    ITUNES_ARTWORK_HIGH_RES,
    MIN_IMAGE_SIZE_BYTES,
    QUALITY_SCORE_COMPILATION,
    QUALITY_SCORE_DELUXE_REMASTER,
    QUALITY_SCORE_SINGLE_EP,
    QUALITY_SCORE_STANDARD,
    QUALITY_SCORE_STUDIO_ALBUM,
    TIMEOUT_API_SHORT,
    TIMEOUT_IMAGE_DOWNLOAD,
    USER_AGENTS,
)
from toolkit.core.logging import get_logger
from toolkit.playlists.parser import COMPILATION_KEYWORDS, pre_sanitize_song_line

logger = get_logger(__name__)


def get_random_agent_headers() -> dict[str, str]:
    return {"User-Agent": random.choice(USER_AGENTS)}


def sanitize_search_query(title: Optional[str], artist: Optional[str], filename_fallback: str = "") -> str:
    """Build clean search query from tags or filename using shared pre-sanitization."""
    if title and artist:
        t_clean = re.sub(r"[\(\[\{].*?[\)\]\}]", "", title).strip()
        a_clean = re.sub(r"[\(\[\{].*?[\)\]\}]", "", artist).strip()
        return pre_sanitize_song_line(f"{a_clean} {t_clean}".strip())

    base_name = os.path.splitext(filename_fallback)[0]
    base_clean = base_name.replace("_", " ")
    base_clean = re.sub(r"^\d+[\.\-\s]+", "", base_clean)
    base_clean = re.sub(r"[\(\[\{].*?[\)\]\}]", "", base_clean).strip()
    return pre_sanitize_song_line(base_clean)


def score_album_quality(album_name: str, artist_name: str = "") -> int:
    """
    Quality scoring engine to prioritize official Studio Albums over Compilations and Soundtracks.
    Higher score indicates higher studio quality confidence.
    """
    if not album_name:
        return QUALITY_SCORE_STANDARD

    alb_lower = album_name.lower()
    art_lower = artist_name.lower()

    if any(k in alb_lower for k in COMPILATION_KEYWORDS) or "various" in art_lower:
        return QUALITY_SCORE_COMPILATION
    if "deluxe" in alb_lower or "remaster" in alb_lower or "expanded" in alb_lower:
        return QUALITY_SCORE_DELUXE_REMASTER
    if "single" in alb_lower or "ep" in alb_lower:
        return QUALITY_SCORE_SINGLE_EP
    return QUALITY_SCORE_STUDIO_ALBUM


def get_high_res_artwork_itunes(query: str, target_album: Optional[str] = None) -> Optional[str]:
    """
    Fetch high-res studio cover art URL via iTunes Search API with quality scoring.
    Upgrades low-res thumbnail URLs to uncompressed 1000x1000 image links.
    """
    url = "https://itunes.apple.com/search"
    params = {"term": query, "media": "music", "entity": "song", "limit": 15}

    try:
        res = http_get(url, params=params, headers=get_random_agent_headers(), timeout=TIMEOUT_API_SHORT)
        if res.status_code == 200:
            results = res.json().get("results", [])
            if not results:
                return None

            best_item = None
            best_score = -1

            for item in results:
                alb_name = item.get("collectionName", "")
                art_name = item.get("artistName", "")
                score = score_album_quality(alb_name, art_name)

                if target_album and alb_name and target_album.lower() in alb_name.lower():
                    score += 50

                if score > best_score:
                    best_score = score
                    best_item = item

            if best_item:
                raw_artwork = best_item.get("artworkUrl100", "")
                if raw_artwork:
                    high_res_url = re.sub(r"/\d+x\d+bb\.", f"/{ITUNES_ARTWORK_HIGH_RES}.", raw_artwork)
                    return high_res_url
    except (OSError, ValueError, KeyError) as e:
        logger.warning(f"iTunes artwork search failed for '{query}': {e}")

    return None


def get_high_res_artwork_deezer(query: str) -> Optional[str]:
    """Fallback high-res artwork search via Deezer API (1000x1000)."""
    url = "https://api.deezer.com/search"
    params = {"q": query, "limit": 10}

    try:
        res = http_get(url, params=params, headers=get_random_agent_headers(), timeout=TIMEOUT_API_SHORT)
        if res.status_code == 200:
            results = res.json().get("data", [])
            if not results:
                return None

            for item in results:
                album_obj = item.get("album", {})
                cover_xl = album_obj.get("cover_xl") or album_obj.get("cover_big")
                if cover_xl:
                    return cover_xl
    except (OSError, ValueError, KeyError) as e:
        logger.warning(f"Deezer artwork search failed for '{query}': {e}")

    return None


def fetch_artwork_bytes(artwork_url: str) -> Optional[bytes]:
    """Download image bytes from URL with uncompressed fallback resolution tests."""
    if not artwork_url:
        return None

    test_urls = [artwork_url]
    if ITUNES_ARTWORK_HIGH_RES in artwork_url:
        for size in ITUNES_ARTWORK_FALLBACK_SIZES:
            test_urls.append(artwork_url.replace(ITUNES_ARTWORK_HIGH_RES, size))

    for test_url in test_urls:
        try:
            r = http_get(test_url, headers=get_random_agent_headers(), timeout=TIMEOUT_IMAGE_DOWNLOAD)
            if r.status_code == 200 and len(r.content) > MIN_IMAGE_SIZE_BYTES:
                return r.content
        except OSError as e:
            logger.debug(f"Artwork download failed for {test_url}: {e}")

    return None
