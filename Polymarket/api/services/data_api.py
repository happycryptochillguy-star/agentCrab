"""Data API client — positions, trades, and on-chain activity."""

import logging

import httpx

from api.config import settings
from api.services.http_pool import get_proxy_client
from api.models import Position, Trade, Activity

logger = logging.getLogger("agentcrab.data_api")


async def get_positions(wallet_address: str) -> list[Position]:
    """Get positions for a wallet address from the Data API."""
    client = get_proxy_client()
    resp = await client.get(
        f"{settings.data_api_url}/positions",
        params={"user": wallet_address},
    )
    resp.raise_for_status()
    raw = resp.json()

    positions: list[Position] = []
    for p in raw:
        positions.append(
            Position(
                market_slug=p.get("market_slug") or p.get("slug"),
                question=p.get("question") or p.get("title"),
                outcome=p.get("outcome", ""),
                token_id=p.get("asset", "") or p.get("token_id", ""),
                size=str(p.get("size", "0")),
                avg_price=str(p.get("avgPrice", "")) or None,
                current_price=str(p.get("curPrice", "")) or None,
                pnl=str(p.get("pnl", "")) or None,
                pnl_percent=str(p.get("pnlPercent", "")) or None,
            )
        )
    return positions


async def get_trades(wallet_address: str, limit: int = 50, offset: int = 0) -> list[Trade]:
    """Get trade history for a wallet address."""
    client = get_proxy_client()
    resp = await client.get(
        f"{settings.data_api_url}/trades",
        params={
            "user": wallet_address,
            "limit": limit,
            "offset": offset,
        },
    )
    resp.raise_for_status()
    raw = resp.json()

    trades: list[Trade] = []
    for t in raw:
        trades.append(
            Trade(
                trade_id=str(t.get("id", "")),
                market_slug=t.get("market_slug") or t.get("slug"),
                outcome=t.get("outcome"),
                side=t.get("side", ""),
                size=str(t.get("size", "0")),
                price=str(t.get("price", "0")),
                timestamp=str(t.get("timestamp") or t.get("created_at") or ""),
            )
        )
    return trades


async def get_activity(wallet_address: str, limit: int = 50, offset: int = 0) -> list[Activity]:
    """Get on-chain activity for a wallet address."""
    client = get_proxy_client()
    resp = await client.get(
        f"{settings.data_api_url}/activity",
        params={
            "user": wallet_address,
            "limit": limit,
            "offset": offset,
        },
    )
    resp.raise_for_status()
    raw = resp.json()

    activities: list[Activity] = []
    for a in raw:
        activities.append(
            Activity(
                type=a.get("type", ""),
                token_id=a.get("asset") or a.get("token_id"),
                amount=str(a.get("amount", "")) or None,
                timestamp=str(a.get("timestamp") or a.get("created_at") or ""),
                tx_hash=a.get("transactionHash") or a.get("tx_hash"),
            )
        )
    return activities
