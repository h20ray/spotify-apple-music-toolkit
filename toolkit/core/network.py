"""
Network & Proxy Utilities Module
Multi-OS compatible network handler for Spotify - Apple Music Toolkit.
Handles system & .env proxies, SSL cert verification, User-Agent rotation,
and IPv4/IPv6 fallback across Windows, macOS, and Linux.
"""

from __future__ import annotations

import os
import socket
from typing import Any, Optional

import requests
from dotenv import load_dotenv

from toolkit.core.constants import DEFAULT_USER_AGENT, TIMEOUT_API_LONG
from toolkit.core.logging import get_logger

load_dotenv()

logger = get_logger(__name__)


def configure_socket_ipv4_fallback() -> None:
    """
    Prefer IPv4 when Apple CDN rate-limits IPv6.
    Skip override when explicit proxy env vars set.
    """
    if get_proxy_config():
        return
    try:
        import urllib3.util.connection as urllib_conn

        def allowed_gai_family():
            return socket.AF_INET

        urllib_conn.allowed_gai_family = allowed_gai_family
    except (ImportError, AttributeError) as e:
        logger.debug(f"IPv4 fallback not applied: {e}")


def get_proxy_config() -> Optional[dict[str, str]]:
    """Return HTTP/HTTPS proxy dict from env, or None."""
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    no_proxy = os.getenv("NO_PROXY") or os.getenv("no_proxy")

    proxies: dict[str, str] = {}
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy

    if proxies:
        if no_proxy:
            os.environ["NO_PROXY"] = no_proxy
            os.environ["no_proxy"] = no_proxy
        return proxies
    return None


_SHARED_SESSION: Optional[requests.Session] = None


def get_network_session(renew: bool = False) -> requests.Session:
    """Return pooled requests.Session with proxy + default headers."""
    global _SHARED_SESSION
    if _SHARED_SESSION is not None and not renew:
        return _SHARED_SESSION

    session = requests.Session()

    adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=1)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    proxies = get_proxy_config()
    if proxies:
        session.proxies.update(proxies)

    session.headers.update({
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    })

    ca_bundle = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE")
    if ca_bundle and os.path.exists(ca_bundle):
        session.verify = ca_bundle

    _SHARED_SESSION = session
    return session


def http_get(
    url: str,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = TIMEOUT_API_LONG,
    session: Optional[requests.Session] = None,
    **kwargs: Any,
) -> requests.Response:
    """Unified HTTP GET with connection pooling and proxy handling."""
    sess = session or get_network_session()
    req_headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        req_headers.update(headers)
    return sess.get(url, params=params, headers=req_headers, timeout=timeout, **kwargs)


def http_post(
    url: str,
    data: Any = None,
    json: Any = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = TIMEOUT_API_LONG,
    session: Optional[requests.Session] = None,
    **kwargs: Any,
) -> requests.Response:
    """Unified HTTP POST with connection pooling and proxy handling."""
    sess = session or get_network_session()
    req_headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        req_headers.update(headers)
    return sess.post(url, data=data, json=json, headers=req_headers, timeout=timeout, **kwargs)


configure_socket_ipv4_fallback()
