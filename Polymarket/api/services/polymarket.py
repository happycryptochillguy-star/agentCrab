import httpx

from api.config import settings
from api.models import FootballEvent, Market, MarketOutcome

# League slug mapping for filtering
LEAGUE_SLUGS = {
    "premier_league": "premier-league",
    "la_liga": "la-liga",
    "ucl": "champions-league",
    "champions_league": "champions-league",
    "serie_a": "serie-a",
    "bundesliga": "bundesliga",
    "ligue_1": "ligue-1",
    "mls": "mls",
    "world_cup": "world-cup",
    "europa_league": "europa-league",
}


async def fetch_football_events(
    league: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[FootballEvent]:
    """Fetch active football/soccer events from Polymarket Gamma API."""
    params: dict = {
        "tag_slug": "soccer",
        "active": "true",
        "closed": "false",
        "limit": limit,
        "offset": offset,
        "order": "volume",
        "ascending": "false",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{settings.gamma_api_url}/events", params=params)
        resp.raise_for_status()
        raw_events = resp.json()

    events: list[FootballEvent] = []
    for ev in raw_events:
        # Filter by league if specified
        if league:
            slug_filter = LEAGUE_SLUGS.get(league, league)
            event_slug = ev.get("slug", "") or ""
            event_title = ev.get("title", "") or ""
            if slug_filter.lower() not in event_slug.lower() and slug_filter.lower() not in event_title.lower():
                continue

        markets: list[Market] = []
        for mkt in ev.get("markets", []):
            outcomes_raw = mkt.get("outcomes", "")
            prices_raw = mkt.get("outcomePrices", "")
            tokens_raw = mkt.get("clobTokenIds", "")

            # Parse JSON string arrays
            if isinstance(outcomes_raw, str):
                try:
                    import json
                    outcomes_list = json.loads(outcomes_raw)
                except Exception:
                    outcomes_list = []
            else:
                outcomes_list = outcomes_raw or []

            if isinstance(prices_raw, str):
                try:
                    import json
                    prices_list = json.loads(prices_raw)
                except Exception:
                    prices_list = []
            else:
                prices_list = prices_raw or []

            if isinstance(tokens_raw, str):
                try:
                    import json
                    tokens_list = json.loads(tokens_raw)
                except Exception:
                    tokens_list = []
            else:
                tokens_list = tokens_raw or []

            outcomes: list[MarketOutcome] = []
            for i, name in enumerate(outcomes_list):
                price = float(prices_list[i]) if i < len(prices_list) else None
                token_id = str(tokens_list[i]) if i < len(tokens_list) else None
                outcomes.append(MarketOutcome(outcome=name, price=price, token_id=token_id))

            markets.append(
                Market(
                    question=mkt.get("question", ""),
                    market_slug=mkt.get("slug"),
                    outcomes=outcomes,
                    volume=_parse_float(mkt.get("volume")),
                    liquidity=_parse_float(mkt.get("liquidity")),
                    end_date=mkt.get("endDate"),
                    active=mkt.get("active", True),
                )
            )

        events.append(
            FootballEvent(
                event_id=str(ev.get("id", "")),
                title=ev.get("title", ""),
                slug=ev.get("slug"),
                markets=markets,
                volume=_parse_float(ev.get("volume")),
                start_date=ev.get("startDate"),
                end_date=ev.get("endDate"),
            )
        )

    return events


def _parse_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
