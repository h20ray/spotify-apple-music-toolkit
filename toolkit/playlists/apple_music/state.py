"""Shared Apple Music module state (cache, tokens, UI console)."""
from __future__ import annotations

import os
from threading import Lock
from typing import Any, Optional

from rich.console import Console

from toolkit.core import CACHE_DIR, EXPORT_APPLE_MUSIC_DIR
from toolkit.core.logging import get_logger

console = Console()
logger = get_logger("toolkit.playlists.apple_music")

SOURCE_FOLDER_NAME = "playlist_sources"
EXPORT_FOLDER_NAME = os.path.join("playlist_exports", "apple_music")

RATE_LIMIT_LOCK = Lock()
LAST_REQUEST_TIME = [0.0]
CACHED_BEARER_TOKEN: list[Optional[str]] = [None]

CACHE_FILE = os.path.join(CACHE_DIR, "apple_music_search_cache.json")
LEGACY_CACHE_FILE = os.path.join(EXPORT_APPLE_MUSIC_DIR, "search_cache.json")
SEARCH_CACHE: dict[str, Any] = {}
