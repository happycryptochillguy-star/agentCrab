"""General Gamma API client for all-category market search."""

import json
import logging

import httpx

from api.config import settings
from api.models import GammaEvent, GammaMarketDetail, Market, MarketOutcome

logger = logging.getLogger("agentcrab.gamma")


def _parse_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_json_str(val) -> list:
    """Parse a JSON string array (Gamma API returns stringified arrays)."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return val or []


def _parse_market(mkt: dict) -> Market:
    """Parse a raw Gamma API market object into our Market model."""
    outcomes_list = _parse_json_str(mkt.get("outcomes", ""))
    prices_list = _parse_json_str(mkt.get("outcomePrices", ""))
    tokens_list = _parse_json_str(mkt.get("clobTokenIds", ""))

    outcomes: list[MarketOutcome] = []
    for i, name in enumerate(outcomes_list):
        price = float(prices_list[i]) if i < len(prices_list) else None
        token_id = str(tokens_list[i]) if i < len(tokens_list) else None
        outcomes.append(MarketOutcome(outcome=name, price=price, token_id=token_id))

    return Market(
        question=mkt.get("question", ""),
        market_slug=mkt.get("slug"),
        outcomes=outcomes,
        volume=_parse_float(mkt.get("volume")),
        liquidity=_parse_float(mkt.get("liquidity")),
        end_date=mkt.get("endDate"),
        active=mkt.get("active", True),
    )


def _parse_tags(ev: dict) -> list[str]:
    """Extract tag slugs from an event."""
    tags_raw = ev.get("tags", [])
    if isinstance(tags_raw, list):
        return [t.get("slug", "") if isinstance(t, dict) else str(t) for t in tags_raw]
    return []


async def search_events(
    query: str | None = None,
    tag: str | None = None,
    limit: int = 20,
    offset: int = 0,
    closed: bool = False,
) -> list[GammaEvent]:
    """Search events across all categories on Gamma API."""
    params: dict = {
        "limit": limit,
        "offset": offset,
        "order": "volume",
        "ascending": "false",
        "active": "true",
        "closed": str(closed).lower(),
    }
    if tag:
        params["tag_slug"] = tag
    if query:
        params["title"] = query  # Gamma API filters by title substring

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{settings.gamma_api_url}/events", params=params)
        resp.raise_for_status()
        raw_events = resp.json()

    events: list[GammaEvent] = []
    for ev in raw_events:
        markets = [_parse_market(m) for m in ev.get("markets", [])]
        events.append(
            GammaEvent(
                event_id=str(ev.get("id", "")),
                title=ev.get("title", ""),
                slug=ev.get("slug"),
                description=ev.get("description"),
                markets=markets,
                volume=_parse_float(ev.get("volume")),
                liquidity=_parse_float(ev.get("liquidity")),
                start_date=ev.get("startDate"),
                end_date=ev.get("endDate"),
                tags=_parse_tags(ev),
                image=ev.get("image"),
            )
        )

    return events


async def get_event_by_id(event_id: str) -> GammaEvent | None:
    """Get a specific event by ID."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{settings.gamma_api_url}/events/{event_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        ev = resp.json()

    markets = [_parse_market(m) for m in ev.get("markets", [])]
    return GammaEvent(
        event_id=str(ev.get("id", "")),
        title=ev.get("title", ""),
        slug=ev.get("slug"),
        description=ev.get("description"),
        markets=markets,
        volume=_parse_float(ev.get("volume")),
        liquidity=_parse_float(ev.get("liquidity")),
        start_date=ev.get("startDate"),
        end_date=ev.get("endDate"),
        tags=_parse_tags(ev),
        image=ev.get("image"),
    )


async def get_event_by_slug(slug: str) -> GammaEvent | None:
    """Get a specific event by slug."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{settings.gamma_api_url}/events/slug/{slug}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        ev = resp.json()

    markets = [_parse_market(m) for m in ev.get("markets", [])]
    return GammaEvent(
        event_id=str(ev.get("id", "")),
        title=ev.get("title", ""),
        slug=ev.get("slug"),
        description=ev.get("description"),
        markets=markets,
        volume=_parse_float(ev.get("volume")),
        liquidity=_parse_float(ev.get("liquidity")),
        start_date=ev.get("startDate"),
        end_date=ev.get("endDate"),
        tags=_parse_tags(ev),
        image=ev.get("image"),
    )


async def get_market_by_id(market_id: str) -> GammaMarketDetail | None:
    """Get a specific market by ID."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{settings.gamma_api_url}/markets/{market_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        mkt = resp.json()

    outcomes_list = _parse_json_str(mkt.get("outcomes", ""))
    prices_list = _parse_json_str(mkt.get("outcomePrices", ""))
    tokens_list = _parse_json_str(mkt.get("clobTokenIds", ""))

    outcomes: list[MarketOutcome] = []
    for i, name in enumerate(outcomes_list):
        price = float(prices_list[i]) if i < len(prices_list) else None
        token_id = str(tokens_list[i]) if i < len(tokens_list) else None
        outcomes.append(MarketOutcome(outcome=name, price=price, token_id=token_id))

    tags_raw = mkt.get("tags", [])
    tags = [t.get("slug", "") if isinstance(t, dict) else str(t) for t in tags_raw] if isinstance(tags_raw, list) else []

    return GammaMarketDetail(
        market_id=str(mkt.get("id", "")),
        question=mkt.get("question", ""),
        description=mkt.get("description"),
        market_slug=mkt.get("slug"),
        condition_id=mkt.get("conditionId"),
        outcomes=outcomes,
        volume=_parse_float(mkt.get("volume")),
        liquidity=_parse_float(mkt.get("liquidity")),
        end_date=mkt.get("endDate"),
        active=mkt.get("active", True),
        closed=mkt.get("closed", False),
        tags=tags,
        image=mkt.get("image"),
    )


async def get_tags() -> list[dict]:
    """Get all available Polymarket tags."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{settings.gamma_api_url}/tags")
        resp.raise_for_status()
        return resp.json()
