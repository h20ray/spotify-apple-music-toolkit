"""Apple Music cloud playlist creation and developer token extraction."""
from __future__ import annotations

import re
import time

from toolkit.core import APPLE_MUSIC_DEVELOPER_TOKEN, APPLE_MUSIC_USER_TOKEN, http_get, http_post
from toolkit.core.constants import (
    APPLE_MUSIC_API_CHUNK_SIZE,
    APPLE_MUSIC_API_RETRY_DELAY,
    MAX_RETRY_ATTEMPTS,
    TIMEOUT_API_LONG,
    TIMEOUT_API_SHORT,
    USER_AGENTS,
)
from toolkit.playlists.apple_music.state import CACHED_BEARER_TOKEN, CACHED_STOREFRONT, console, logger

API_BASE = "https://amp-api.music.apple.com"
DEFAULT_STOREFRONT = "us"


def get_user_storefront() -> str:
    """Return the user's Apple Music storefront (e.g. 'id'), so searches return IDs addable to their library.

    Falls back to 'us' when no user token is configured or the lookup fails.
    """
    if CACHED_STOREFRONT[0]:
        return CACHED_STOREFRONT[0]

    storefront = DEFAULT_STOREFRONT
    dev_token = get_apple_developer_token()
    if APPLE_MUSIC_USER_TOKEN and dev_token:
        try:
            resp = http_get(
                f"{API_BASE}/v1/me/storefront",
                headers=catalog_headers(dev_token),
                timeout=TIMEOUT_API_SHORT,
            )
            if resp.status_code == 200:
                storefront = resp.json()["data"][0]["id"]
            else:
                logger.warning(f"Storefront lookup returned {resp.status_code}; using '{DEFAULT_STOREFRONT}'")
        except (OSError, ValueError, KeyError, IndexError) as e:
            logger.warning(f"Storefront lookup failed, using '{DEFAULT_STOREFRONT}': {e}")

    CACHED_STOREFRONT[0] = storefront
    return storefront


def catalog_headers(dev_token: str) -> dict[str, str]:
    """Headers for amp-api catalog calls; the user token (when set) also gives a separate, larger rate-limit bucket."""
    headers = {
        "Authorization": f"Bearer {dev_token}",
        "Origin": "https://music.apple.com",
        "Referer": "https://music.apple.com/",
    }
    if APPLE_MUSIC_USER_TOKEN:
        headers["Media-User-Token"] = APPLE_MUSIC_USER_TOKEN
    return headers


def _playlist_track_count(playlist_id: str, headers: dict[str, str]) -> int | None:
    """Count tracks currently in a library playlist, or None if it can't be read."""
    count, url = 0, f"/v1/me/library/playlists/{playlist_id}/tracks?limit=100"
    try:
        while url:
            resp = http_get(API_BASE + url, headers=headers, timeout=TIMEOUT_API_LONG)
            if resp.status_code == 404:  # empty playlist has no tracks relationship yet
                return count
            if resp.status_code != 200:
                return None
            body = resp.json()
            count += len(body.get("data", []))
            url = body.get("next")
    except (OSError, ValueError) as e:
        logger.warning(f"Could not read playlist size: {e}")
        return None
    return count


def get_apple_developer_token():
    """Dynamically extract Apple Music Web Developer Bearer Token using network HTTP helper."""
    if CACHED_BEARER_TOKEN[0]:
        return CACHED_BEARER_TOKEN[0]

    dev_env = APPLE_MUSIC_DEVELOPER_TOKEN
    if dev_env:
        CACHED_BEARER_TOKEN[0] = dev_env
        return dev_env

    headers = {"User-Agent": USER_AGENTS[0]}
    try:
        # The JS bundle name changes on every web player deploy and old bundles keep serving
        # expired tokens, so discover the current bundle from the page HTML.
        page = http_get("https://music.apple.com/us/browse", headers=headers, timeout=TIMEOUT_API_SHORT)
        bundles = re.findall(r'/assets/index[^"\']*?\.js', page.text)
        for bundle in dict.fromkeys(bundles):
            res = http_get(f"https://music.apple.com{bundle}", headers=headers, timeout=TIMEOUT_API_SHORT)
            tokens = re.findall(r"ey[A-Za-z0-9\-_=]{20,}\.ey[A-Za-z0-9\-_=]{20,}\.[A-Za-z0-9\-_=]{20,}", res.text)
            if tokens:
                CACHED_BEARER_TOKEN[0] = tokens[0]
                return tokens[0]
    except (OSError, ValueError) as e:
        logger.warning(f"Failed fetching Apple developer token: {e}")

    return None


def create_apple_music_cloud_playlist(playlist_name, tracks, user_token=None):
    """
    Directly create playlist in user's Apple Music Cloud account via official Apple Music API.
    Zero third-party website dependency! Uses 2-step batch chunking strategy with rate-limit delays.
    """
    u_token = user_token or APPLE_MUSIC_USER_TOKEN
    if not u_token:
        console.print(
            "[bold yellow]Notice: APPLE_MUSIC_USER_TOKEN not set in .env. Skipping direct Cloud"
            "Sync.[/bold yellow]"
        )
        return False

    dev_token = get_apple_developer_token()
    if not dev_token:
        console.print("[bold red]Error: Unable to fetch Apple Music developer token.[/bold red]")
        return False

    url_create = "https://amp-api.music.apple.com/v1/me/library/playlists"
    headers = {
        "Authorization": f"Bearer {dev_token}",
        "Music-User-Token": u_token,
        "Content-Type": "application/json",
        "Origin": "https://music.apple.com",
        "Referer": "https://music.apple.com/"
    }

    payload_create = {
        "attributes": {
            "name": playlist_name,
            "description": "Generated by Spotify - Apple Music Toolkit"
        }
    }

    try:
        resp = http_post(url_create, json=payload_create, headers=headers, timeout=TIMEOUT_API_LONG)
        if resp.status_code in [200, 201]:
            data = resp.json().get("data", [])
            if not data:
                console.print("[bold red]API Error:[/bold red] Could not parse created playlist ID.")
                return False

            playlist_id = data[0]["id"]
            console.print(f"[bold cyan]Playlist Container Created! (ID: {playlist_id})[/bold cyan]")

            track_ids = [item.get("trackId") for item in tracks if item.get("trackId")]
            all_track_objs = [{"id": str(tid), "type": "songs"} for tid in track_ids]

            url_add = f"https://amp-api.music.apple.com/v1/me/library/playlists/{playlist_id}/tracks"
            chunk_size = APPLE_MUSIC_API_CHUNK_SIZE
            added_count = 0

            for i in range(0, len(all_track_objs), chunk_size):
                chunk = all_track_objs[i : i + chunk_size]
                time.sleep(0.3)

                for attempt in range(MAX_RETRY_ATTEMPTS):
                    resp_add = http_post(url_add, json={"data": chunk}, headers=headers, timeout=TIMEOUT_API_LONG)
                    applied = resp_add.status_code in [200, 201, 204]
                    if not applied and resp_add.status_code >= 500:
                        # Cloud Library often returns 500 even though the tracks were added; retrying blindly
                        # duplicates them, so check the playlist size before deciding to resend.
                        time.sleep(APPLE_MUSIC_API_RETRY_DELAY * 2)
                        applied = _playlist_track_count(playlist_id, headers) == added_count + len(chunk)
                    if applied:
                        added_count += len(chunk)
                        console.print(
                            f"[dim]Synced {added_count}/{len(all_track_objs)} tracks to Apple Music Cloud...[/dim]"
                        )
                        break
                    if resp_add.status_code == 429 or resp_add.status_code >= 500:
                        time.sleep(APPLE_MUSIC_API_RETRY_DELAY * (attempt + 1))
                    else:
                        console.print(
                            f"[bold yellow]Batch Add Notice "
                            f"({resp_add.status_code}):[/bold yellow] "
                            f"{resp_add.text[:150]}"
                        )
                        break

            console.print(
                f"[bold green]✓ SUCCESS! Playlist '{playlist_name}' "
                f"({added_count} tracks) synced directly to your "
                f"Apple Music Account![/bold green]"
            )
            return True
        console.print(f"[bold yellow]Apple Music API Notice ({resp.status_code}):[/bold yellow] {resp.text[:200]}")
    except (OSError, ValueError, KeyError) as e:
        logger.error(f"Apple Music cloud playlist API error: {e}")
        console.print(f"[bold red]API Exception:[/bold red] {e}")

    return False
