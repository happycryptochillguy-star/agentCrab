"""Historical events database — sync closed Polymarket events and query them."""

import json
import logging
import time

import aiosqlite
import httpx

from api.config import settings
from api.services.http_pool import get_proxy_client
from api.services.categories import CATEGORIES

logger = logging.getLogger("agentcrab.history")

DB_PATH = settings.db_path

# Track last sync time for throttling
_last_sync_time: float = 0.0
SYNC_COOLDOWN = 3600  # 1 hour

# Periodic sync interval (seconds). Full sync on first run, incremental after.
PERIODIC_SYNC_INTERVAL = 6 * 3600  # 6 hours
INCREMENTAL_MAX_PAGES = 4  # 4 pages × 500 = 2000 events covers recent closures


def _parse_json_str(val) -> list:
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return val or []


def match_category(tag_slugs: list[str]) -> str | None:
    """Given an event's tag slugs, find the best matching category path.

    Walks the CATEGORIES tree depth-first. Returns the deepest node whose
    tag_slugs overlap with the event's tags. If multiple top-level categories
    match, picks the one with the deepest match.
    """
    if not tag_slugs:
        return None

    slug_set = set(tag_slugs)
    best_path: str | None = None
    best_depth = -1

    def _walk(node: dict, path: str, depth: int):
        nonlocal best_path, best_depth
        node_slugs = set(node.get("tag_slugs", []))
        if node_slugs & slug_set:
            if depth > best_depth:
                best_depth = depth
                best_path = path

        subs = node.get("subcategories")
        if subs:
            for key, child in subs.items():
                _walk(child, f"{path}.{key}", depth + 1)

    for top_key, top_node in CATEGORIES.items():
        _walk(top_node, top_key, 0)

    return best_path


def _parse_resolution(event: dict) -> str | None:
    """Determine the winning outcome(s) from a closed event's markets.

    For each market, the outcome with price >= 0.95 is considered the winner.
    Multi-market events join winners with "; ".
    """
    markets = event.get("markets", [])
    if not markets:
        return None

    winners: list[str] = []
    for mkt in markets:
        outcomes = _parse_json_str(mkt.get("outcomes", ""))
        prices = _parse_json_str(mkt.get("outcomePrices", ""))
        for i, name in enumerate(outcomes):
            if i < len(prices):
                try:
                    p = float(prices[i])
                except (ValueError, TypeError):
                    continue
                if p >= 0.95:
                    winners.append(name)
                    break  # one winner per market

    return "; ".join(winners) if winners else None


def _parse_tags(ev: dict) -> list[str]:
    tags_raw = ev.get("tags", [])
    if isinstance(tags_raw, list):
        return [t.get("slug", "") if isinstance(t, dict) else str(t) for t in tags_raw]
    return []


def _parse_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


async def sync_historical_events(max_pages: int = 0) -> int:
    """Scrape closed events from Gamma API and store in SQLite.

    Paginates through closed events sorted by volume descending.
    max_pages=0 means no limit (full sync). max_pages>0 limits to N pages
    (incremental — newly closed events have recent volume so appear early).
    Returns the total number of events synced.
    """
    global _last_sync_time

    total_synced = 0
    offset = 0
    page_size = 500
    pages_fetched = 0
    now = time.time()

    mode = "incremental" if max_pages else "full"
    logger.info(f"Starting {mode} historical events sync (max_pages={max_pages or 'unlimited'})...")

    client = get_proxy_client()
    while True:
        params = {
            "limit": page_size,
            "offset": offset,
            "order": "volume",
            "ascending": "false",
            "closed": "true",
        }
        try:
            resp = await client.get(
                f"{settings.gamma_api_url}/events", params=params
            )
            resp.raise_for_status()
            raw_events = resp.json()
        except Exception as e:
            logger.warning(f"Failed to fetch closed events at offset {offset}: {e}")
            pages_fetched += 1
            offset += page_size
            continue

        if not raw_events:
            break

        rows: list[tuple] = []
        for ev in raw_events:
            event_id = str(ev.get("id", ""))
            title = ev.get("title", "")
            tag_slugs = _parse_tags(ev)
            category = match_category(tag_slugs)
            resolution = _parse_resolution(ev)
            volume = _parse_float(ev.get("volume"))
            market_count = len(ev.get("markets", []))

            rows.append((
                event_id,
                title,
                category,
                ev.get("startDate"),
                ev.get("endDate"),
                ev.get("closedTime") or ev.get("endDate"),
                volume,
                resolution,
                json.dumps(tag_slugs),
                market_count,
                now,
            ))

        async with aiosqlite.connect(DB_PATH) as db:
            await db.executemany(
                """INSERT OR REPLACE INTO historical_events
                   (event_id, title, category, start_date, end_date, closed_time,
                    volume, resolution, tags, market_count, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            await db.commit()

        total_synced += len(raw_events)
        pages_fetched += 1
        logger.info(f"Synced {total_synced} events so far (page={pages_fetched}, offset={offset})...")

        if len(raw_events) < page_size:
            break

        if max_pages and pages_fetched >= max_pages:
            logger.info(f"Incremental sync limit reached ({max_pages} pages).")
            break

        offset += page_size

    if total_synced > 0:
        _last_sync_time = time.time()
    logger.info(f"Historical events sync complete: {total_synced} events.")
    return total_synced


async def search_history(
    query: str | None = None,
    category: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Query historical events from SQLite."""
    conditions: list[str] = []
    params: list = []

    if query:
        conditions.append("title LIKE ? COLLATE NOCASE")
        params.append(f"%{query}%")

    if category:
        conditions.append("category LIKE ?")
        params.append(f"{category}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sql = f"""
        SELECT event_id, title, category, start_date, end_date, closed_time,
               volume, resolution, tags, market_count
        FROM historical_events
        {where}
        ORDER BY volume DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(sql, params)

    results: list[dict] = []
    for row in rows:
        r = dict(row)
        # Parse tags JSON back to list
        if r.get("tags"):
            try:
                r["tags"] = json.loads(r["tags"])
            except Exception:
                r["tags"] = []
        results.append(r)

    return results


async def get_history_stats() -> dict:
    """Return stats about the historical events database."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Total count
        row = await db.execute_fetchall("SELECT COUNT(*) FROM historical_events")
        total = row[0][0] if row else 0

        if total == 0:
            return {"total_events": 0, "categories": {}, "last_sync": None}

        # Date range
        row = await db.execute_fetchall(
            "SELECT MIN(start_date), MAX(end_date) FROM historical_events"
        )
        earliest = row[0][0] if row else None
        latest = row[0][1] if row else None

        # Category breakdown
        rows = await db.execute_fetchall(
            "SELECT category, COUNT(*) FROM historical_events GROUP BY category ORDER BY COUNT(*) DESC"
        )
        categories = {r[0] or "uncategorized": r[1] for r in rows}

        # Last sync
        row = await db.execute_fetchall(
            "SELECT MAX(synced_at) FROM historical_events"
        )
        last_sync = row[0][0] if row else None

    return {
        "total_events": total,
        "date_range": {"earliest": earliest, "latest": latest},
        "categories": categories,
        "last_sync": last_sync,
    }


def can_sync() -> bool:
    """Check if enough time has passed since the last sync."""
    return (time.time() - _last_sync_time) >= SYNC_COOLDOWN


async def is_empty() -> bool:
    """Check if the historical_events table is empty."""
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall(
            "SELECT COUNT(*) FROM historical_events"
        )
        return row[0][0] == 0
