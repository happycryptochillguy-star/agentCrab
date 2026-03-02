"""General Gamma API client for all-category market search."""

import asyncio
import json
import logging
import time
from collections import OrderedDict

import httpx

from api.config import settings
from api.models import GammaEvent, GammaMarketDetail, Market, MarketOutcome
from api.services.http_pool import get_proxy_client

logger = logging.getLogger("agentcrab.gamma")


# === LRU + TTL cache for search results ===

_search_cache: OrderedDict[str, tuple[float, list]] = OrderedDict()  # key -> (timestamp, results)
_CACHE_TTL = 60  # seconds
_CACHE_MAX_ENTRIES = 200


def _cache_key(query: str | None, tag: str | None, limit: int, offset: int, closed: bool) -> str:
    return f"{query}|{tag}|{limit}|{offset}|{closed}"


def _cache_get(key: str) -> list | None:
    """Get from cache if fresh. Returns None if miss or stale."""
    entry = _search_cache.get(key)
    if entry is None:
        return None
    ts, results = entry
    if time.time() - ts > _CACHE_TTL:
        _search_cache.pop(key, None)
        return None
    # Move to end (most recently used)
    _search_cache.move_to_end(key)
    return results


def _cache_put(key: str, results: list):
    """Store results in cache. Evicts oldest if over max size."""
    _search_cache[key] = (time.time(), results)
    _search_cache.move_to_end(key)
    while len(_search_cache) > _CACHE_MAX_ENTRIES:
        _search_cache.popitem(last=False)


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
        condition_id=mkt.get("conditionId"),
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


# Keyword → Gamma tag_slug mapping for auto-detection.
# Each keyword (lowercase) maps to a tag_slug that narrows Gamma API results.
_TAG_KEYWORDS: dict[str, str] = {
    "nba": "nba", "basketball": "nba",
    "nfl": "nfl", "football": "nfl", "super bowl": "nfl", "superbowl": "nfl",
    "soccer": "soccer", "epl": "EPL", "premier league": "EPL",
    "champions league": "ucl", "ucl": "ucl",
    "la liga": "la-liga", "ligue 1": "ligue-1",
    "f1": "f1", "formula 1": "formula1", "formula1": "formula1",
    "mlb": "mlb", "baseball": "mlb",
    "nhl": "nhl", "hockey": "nhl",
    "ufc": "ufc", "mma": "ufc", "boxing": "boxing",
    "tennis": "tennis",
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "solana": "solana", "sol": "solana",
    "crypto": "crypto",
    "trump": "trump",
    "election": "elections", "elections": "elections",
    "fed": "fed", "federal reserve": "fed",
    "ai": "ai", "openai": "openai",
}


def _infer_tag(query: str) -> str | None:
    """Auto-detect a Gamma tag_slug from query keywords.

    Checks multi-word phrases first, then single words.
    Returns the first match or None.
    """
    q = query.lower()
    # Check multi-word phrases first (longer matches are more specific)
    for phrase in sorted(_TAG_KEYWORDS, key=len, reverse=True):
        if " " in phrase and phrase in q:
            return _TAG_KEYWORDS[phrase]
    # Then single words
    for word in q.split():
        word = word.strip(".,!?\"'")
        if word in _TAG_KEYWORDS:
            return _TAG_KEYWORDS[word]
    return None


def _smart_filter(events: list[GammaEvent], query: str) -> list[GammaEvent]:
    """Score-based search: split query into words, match against title + market questions.

    Scoring:
    - Exact full query in title:  +100
    - Each word found in title:   +10
    - Each word found in ANY market question: +5  (boolean per word, not per market)
    - Results sorted by score (desc), then volume (desc)

    The market question score is capped per word (not per market) to prevent
    events with many sub-markets (e.g. stat leaders with 50 player outcomes)
    from outscoring events with exact title matches.
    """
    words = [w.lower() for w in query.lower().split() if len(w) >= 2]
    if not words:
        return events

    scored: list[tuple[int, GammaEvent]] = []
    q_lower = query.lower()

    for ev in events:
        score = 0
        title_lower = ev.title.lower()

        # Exact full query match in title
        if q_lower in title_lower:
            score += 100

        # Per-word matching in title
        for w in words:
            if w in title_lower:
                score += 10

        # Per-word matching in market questions (boolean: +5 if word appears
        # in ANY market question, regardless of how many markets contain it)
        for w in words:
            if any(w in mkt.question.lower() for mkt in ev.markets):
                score += 5

        if score > 0:
            scored.append((score, ev))

    scored.sort(key=lambda x: (x[0], x[1].volume or 0), reverse=True)
    return [ev for _, ev in scored]


async def search_events(
    query: str | None = None,
    tag: str | None = None,
    limit: int = 20,
    offset: int = 0,
    closed: bool = False,
) -> list[GammaEvent]:
    """Search events across all categories on Gamma API.

    NOTE: Gamma API's `title` param does NOT filter by title — it's ignored.
    We fetch a larger batch and do client-side title matching when `query` is set.
    The `tag_slug` param works correctly for category filtering.

    When no tag is provided, we auto-detect tags from the query keywords
    (e.g. "NBA Champion" → tag_slug=nba) to narrow the Gamma API results.
    If auto-tag produces poor results, we fall back to untagged broad search.
    """
    # Check cache first
    ck = _cache_key(query, tag, limit, offset, closed)
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    # Auto-detect tag from query keywords when no explicit tag is provided.
    # This dramatically improves search for queries like "NBA Champion",
    # "Bitcoin price", "Trump election" by narrowing the Gamma API results.
    auto_tag = None
    if query and not tag:
        auto_tag = _infer_tag(query)

    events = await _fetch_search_results(query, tag or auto_tag, limit, offset, closed)

    # If auto-tag produced too few results, fall back to broad untagged search
    if auto_tag and len(events) < limit:
        broad = await _fetch_search_results(query, None, limit, offset, closed)
        # Merge: auto-tag results first (better precision), then broad results
        seen_ids = {e.event_id for e in events}
        for ev in broad:
            if ev.event_id not in seen_ids:
                events.append(ev)
                seen_ids.add(ev.event_id)

    # Client-side smart search (Gamma API doesn't support text search)
    if query:
        events = _smart_filter(events, query)
        events = events[offset : offset + limit]

    _cache_put(ck, events)
    return events


async def _fetch_search_results(
    query: str | None,
    tag: str | None,
    limit: int,
    offset: int,
    closed: bool,
) -> list[GammaEvent]:
    """Fetch raw events from Gamma API for search."""
    if query and not tag:
        fetch_limit = max(limit * 10, 500)
    elif query:
        fetch_limit = limit * 5
    else:
        fetch_limit = limit
    fetch_offset = 0 if query else offset

    params: dict = {
        "limit": fetch_limit,
        "offset": fetch_offset,
        "order": "volume",
        "ascending": "false",
        "active": "true",
        "closed": str(closed).lower(),
    }
    if tag:
        params["tag_slug"] = tag

    client = get_proxy_client()
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
    client = get_proxy_client()
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
    client = get_proxy_client()
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
    client = get_proxy_client()
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


VALID_MOODS = {"trending", "interesting", "controversial", "new", "closing_soon"}

MOOD_LABELS = {
    "trending": "Trending (highest volume)",
    "interesting": "Interesting (curated mix)",
    "controversial": "Controversial (most divided opinion)",
    "new": "New (recently created)",
    "closing_soon": "Closing Soon (ending within 7 days)",
}


async def browse_by_mood(
    mood: str, limit: int = 20, offset: int = 0
) -> list[GammaEvent]:
    """Fetch events by mood keyword. Each mood maps to a different query strategy."""
    if mood not in VALID_MOODS:
        return []

    if mood == "trending":
        return await _mood_trending(limit, offset)
    elif mood == "new":
        return await _mood_new(limit, offset)
    elif mood == "closing_soon":
        return await _mood_closing_soon(limit, offset)
    elif mood == "controversial":
        return await _mood_controversial(limit, offset)
    elif mood == "interesting":
        return await _mood_interesting(limit, offset)
    return []


async def _fetch_events_raw(
    order: str = "volume",
    ascending: bool = False,
    limit: int = 50,
    offset: int = 0,
    active: bool = True,
    closed: bool = False,
) -> list[GammaEvent]:
    """Low-level fetch from Gamma with configurable sort."""
    params: dict = {
        "limit": limit,
        "offset": offset,
        "order": order,
        "ascending": str(ascending).lower(),
        "active": str(active).lower(),
        "closed": str(closed).lower(),
    }
    client = get_proxy_client()
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


async def _mood_trending(limit: int, offset: int) -> list[GammaEvent]:
    """Highest volume active events."""
    return await _fetch_events_raw(order="volume", limit=limit, offset=offset)


async def _mood_new(limit: int, offset: int) -> list[GammaEvent]:
    """Most recently created events."""
    return await _fetch_events_raw(
        order="startDate", ascending=False, limit=limit, offset=offset
    )


async def _mood_closing_soon(limit: int, offset: int) -> list[GammaEvent]:
    """Events ending soonest (still active)."""
    return await _fetch_events_raw(
        order="endDate", ascending=True, limit=limit, offset=offset
    )


async def _mood_controversial(limit: int, offset: int) -> list[GammaEvent]:
    """Events where at least one market has outcomes near 50/50 split.

    Fetch top-volume events, filter for markets with price between 0.40–0.60.
    """
    batch = await _fetch_events_raw(order="volume", limit=max(limit * 5, 100))
    controversial: list[GammaEvent] = []
    for ev in batch:
        for mkt in ev.markets:
            prices = [o.price for o in mkt.outcomes if o.price is not None]
            if any(0.40 <= p <= 0.60 for p in prices):
                controversial.append(ev)
                break
    return controversial[offset : offset + limit]


async def _mood_interesting(limit: int, offset: int) -> list[GammaEvent]:
    """Curated mix: top trending + newest + most controversial, deduplicated."""
    trending, new, controversial = await asyncio.gather(
        _mood_trending(limit=10, offset=0),
        _mood_new(limit=10, offset=0),
        _mood_controversial(limit=10, offset=0),
    )
    seen: set[str] = set()
    mixed: list[GammaEvent] = []
    # Interleave: 1 trending, 1 new, 1 controversial, repeat
    sources = [trending, new, controversial]
    max_len = max(len(s) for s in sources) if sources else 0
    for i in range(max_len):
        for src in sources:
            if i < len(src) and src[i].event_id not in seen:
                seen.add(src[i].event_id)
                mixed.append(src[i])
    return mixed[offset : offset + limit]


async def get_tags() -> list[dict]:
    """Get all available Polymarket tags."""
    client = get_proxy_client()
    resp = await client.get(f"{settings.gamma_api_url}/tags")
    resp.raise_for_status()
    return resp.json()


async def browse_by_tags(
    tag_slugs: list[str],
    query: str | None = None,
    limit: int = 20,
    offset: int = 0,
    closed: bool = False,
) -> list[GammaEvent]:
    """Fetch events for multiple tag slugs, deduplicate, and sort by volume.

    If 1 slug: single call. If multiple: parallel calls, merge results.
    """
    if not tag_slugs:
        return []

    if len(tag_slugs) == 1:
        return await search_events(
            query=query, tag=tag_slugs[0], limit=limit, offset=offset, closed=closed
        )

    # Multiple slugs: fetch in parallel (each with generous limit), then merge
    per_slug_limit = max(limit, 50)

    async def _fetch_slug(slug: str) -> list[GammaEvent]:
        return await search_events(
            query=query, tag=slug, limit=per_slug_limit, offset=0, closed=closed
        )

    results = await asyncio.gather(*[_fetch_slug(s) for s in tag_slugs])

    # Deduplicate by event_id
    seen: set[str] = set()
    merged: list[GammaEvent] = []
    for events in results:
        for ev in events:
            if ev.event_id not in seen:
                seen.add(ev.event_id)
                merged.append(ev)

    # Sort by volume descending
    merged.sort(key=lambda e: e.volume or 0, reverse=True)

    # Apply offset/limit
    return merged[offset : offset + limit]
