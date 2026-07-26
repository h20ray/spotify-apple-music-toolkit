"""
Network & Proxy Utilities Module.
Backward compatibility wrapper delegating to toolkit.core.network.
"""

from toolkit.core.network import (
    DEFAULT_USER_AGENT,
    configure_socket_ipv4_fallback,
    get_proxy_config,
    get_network_session,
    http_get,
    http_post,
)

__all__ = [
    "DEFAULT_USER_AGENT",
    "configure_socket_ipv4_fallback",
    "get_proxy_config",
    "get_network_session",
    "http_get",
    "http_post",
]


