"""Tests for network helpers."""

from toolkit.core.network import get_proxy_config


def test_get_proxy_config_none(monkeypatch):
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    assert get_proxy_config() is None


def test_get_proxy_config_from_env(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
    proxies = get_proxy_config()
    assert proxies is not None
    assert proxies["http"] == "http://127.0.0.1:7890"
