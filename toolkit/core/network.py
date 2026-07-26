"""
Network & Proxy Utilities Module
Multi-OS compatible network handler for Spotify - Apple Music Toolkit.
Handles system & .env proxies, SSL cert verification, User-Agent rotation, and IPv4/IPv6 fallback across Windows, macOS, and Linux.
"""

import os
import sys
import socket
import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Apply IPv4 forced resolution if specifically requested or to avoid Apple CDN IPv6 403/429 rate limit blocks
def configure_socket_ipv4_fallback():
    """
    Safely configure socket resolution to prefer IPv4 if Apple CDN rate limiting is encountered.
    Avoids overriding socket family when explicit proxy environment variables are set.
    """
    if get_proxy_config():
        # Do not override socket family when user has configured an explicit proxy
        return
    try:
        import urllib3.util.connection as urllib_conn
        def allowed_gai_family():
            return socket.AF_INET
        urllib_conn.allowed_gai_family = allowed_gai_family
    except Exception:
        pass

def get_proxy_config():
    """
    Retrieve configured HTTP and HTTPS proxies from environment variables or .env file.
    Returns a dictionary of proxies or None if no proxy is configured.
    """
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    no_proxy = os.getenv("NO_PROXY") or os.getenv("no_proxy")

    proxies = {}
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

_SHARED_SESSION = None

def get_network_session(renew=False):
    """
    Create or return a pre-configured, persistent requests.Session with proxy settings,
    standard headers, multi-OS SSL verification, and connection pooling.
    """
    global _SHARED_SESSION
    if _SHARED_SESSION is not None and not renew:
        return _SHARED_SESSION

    session = requests.Session()
    
    # Configure connection pool adapter for performance
    adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=1)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # Configure proxies if available
    proxies = get_proxy_config()
    if proxies:
        session.proxies.update(proxies)
        
    session.headers.update({
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    })

    # SSL certificate fallback check for macOS / Linux
    ca_bundle = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE")
    if ca_bundle and os.path.exists(ca_bundle):
        session.verify = ca_bundle

    _SHARED_SESSION = session
    return session

def http_get(url, params=None, headers=None, timeout=10, session=None, **kwargs):
    """Unified HTTP GET helper with persistent connection pooling and proxy handling."""
    sess = session or get_network_session()
    req_headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        req_headers.update(headers)
    return sess.get(url, params=params, headers=req_headers, timeout=timeout, **kwargs)

def http_post(url, data=None, json=None, headers=None, timeout=10, session=None, **kwargs):
    """Unified HTTP POST helper with persistent connection pooling and proxy handling."""
    sess = session or get_network_session()
    req_headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        req_headers.update(headers)
    return sess.post(url, data=data, json=json, headers=req_headers, timeout=timeout, **kwargs)

# Initialize socket settings on module import
configure_socket_ipv4_fallback()
