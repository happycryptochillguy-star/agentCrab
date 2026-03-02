"""Shared httpx connection pools for all upstream services.

Two pools:
- proxy_client: for Polymarket domains (geo-blocked, via SOCKS5 proxy)
- direct_client: for non-blocked services (blockchain RPCs, Telegram, etc.)

Clients are created lazily on first use and reuse TCP connections.
Call close_all() on shutdown to clean up.
"""

import logging

import httpx

from api.config import settings

logger = logging.getLogger("agentcrab.http_pool")

_proxy_client: httpx.AsyncClient | None = None
_direct_client: httpx.AsyncClient | None = None
_telegram_client: httpx.AsyncClient | None = None


_pool_limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)


def get_proxy_client() -> httpx.AsyncClient:
    """Get the shared proxy client for Polymarket API calls."""
    global _proxy_client
    if _proxy_client is None or _proxy_client.is_closed:
        kwargs: dict = {"timeout": 30, "limits": _pool_limits}
        if settings.polymarket_proxy:
            kwargs["proxy"] = settings.polymarket_proxy
        _proxy_client = httpx.AsyncClient(**kwargs)
    return _proxy_client


def get_direct_client() -> httpx.AsyncClient:
    """Get the shared direct client for non-blocked services."""
    global _direct_client
    if _direct_client is None or _direct_client.is_closed:
        _direct_client = httpx.AsyncClient(timeout=15, limits=_pool_limits)
    return _direct_client


def get_telegram_client() -> httpx.AsyncClient:
    """Get the shared client for Telegram API."""
    global _telegram_client
    if _telegram_client is None or _telegram_client.is_closed:
        kwargs: dict = {"timeout": 10, "limits": _pool_limits}
        if settings.telegram_proxy:
            kwargs["proxy"] = settings.telegram_proxy
        _telegram_client = httpx.AsyncClient(**kwargs)
    return _telegram_client


async def close_all():
    """Close all shared clients. Call on app shutdown."""
    global _proxy_client, _direct_client, _telegram_client
    for name, client in [("proxy", _proxy_client), ("direct", _direct_client), ("telegram", _telegram_client)]:
        if client and not client.is_closed:
            await client.aclose()
            logger.info("Closed %s HTTP pool", name)
    _proxy_client = None
    _direct_client = None
    _telegram_client = None
