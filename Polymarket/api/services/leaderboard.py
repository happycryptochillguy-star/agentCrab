"""Leaderboard and trader lookup service."""

import logging

import httpx

from api.config import settings
from api.services.http_pool import get_proxy_client
from api.models import LeaderboardEntry, Position, Trade

logger = logging.getLogger("agentcrab.leaderboard")


async def get_leaderboard(limit: int = 20, offset: int = 0) -> list[LeaderboardEntry]:
    """Get top traders leaderboard. Paginates automatically if limit > 50."""
    # Cap limit to prevent unbounded upstream pagination loops
    limit = min(limit, 500)
    client = get_proxy_client()
    page_size = 50  # Data API max per request
    max_pages = 20  # Safety bound: max 20 pages (1000 entries)
    all_entries: list[LeaderboardEntry] = []
    current_offset = offset
    pages_fetched = 0

    while len(all_entries) < limit and pages_fetched < max_pages:
        fetch_limit = min(page_size, limit - len(all_entries))
        resp = await client.get(
            f"{settings.data_api_url}/v1/leaderboard",
            params={
                "category": "OVERALL",
                "timePeriod": "ALL",
                "orderBy": "PNL",
                "limit": fetch_limit,
                "offset": current_offset,
            },
        )
        resp.raise_for_status()
        raw = resp.json()
        if not raw:
            break  # No more results

        for r in raw:
            all_entries.append(
                LeaderboardEntry(
                    rank=int(r.get("rank", 0)),
                    address=r.get("proxyWallet", ""),
                    display_name=r.get("userName") or r.get("pseudonym"),
                    volume=str(r.get("vol", "")) or None,
                    pnl=str(r.get("pnl", "")) or None,
                    positions_count=None,
                    trades_count=None,
                )
            )

        pages_fetched += 1
        if len(raw) < fetch_limit:
            break  # Last page
        current_offset += len(raw)

    return all_entries


async def get_trader_positions(address: str) -> list[Position]:
    """Get positions for any trader by wallet address."""
    client = get_proxy_client()
    resp = await client.get(
        f"{settings.data_api_url}/positions",
        params={"user": address},
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


async def get_trader_trades(address: str, limit: int = 50, offset: int = 0) -> list[Trade]:
    """Get trade history for any trader."""
    client = get_proxy_client()
    resp = await client.get(
        f"{settings.data_api_url}/trades",
        params={"user": address, "limit": limit, "offset": offset},
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
                timestamp=t.get("timestamp") or t.get("created_at"),
            )
        )
    return trades
