"""Category Leaderboard — per-category trader rankings.

Background sync fetches top traders + their positions from Polymarket Data API,
resolves each position's market_slug to a category via Gamma API,
then aggregates into per-(trader, category) leaderboard entries in SQLite.
"""

import asyncio
import json
import logging
import time

import httpx

from api.config import settings
from api.services.categories import CATEGORIES
from api.services.history import match_category
from api.services import leaderboard as lb_svc
from api.services.balance import get_db, _write_lock

logger = logging.getLogger("agentcrab.category_lb")

# Sync throttle
_last_sync_time: float = 0.0
SYNC_COOLDOWN = 2 * 3600  # 2 hours

PERIODIC_SYNC_INTERVAL = 4 * 3600  # 4 hours


def _client_kwargs() -> dict:
    kwargs: dict = {"timeout": 30}
    if settings.polymarket_proxy:
        kwargs["proxy"] = settings.polymarket_proxy
    return kwargs


# ---------------------------------------------------------------------------
# Market → Category resolution (cached in SQLite)
# ---------------------------------------------------------------------------


async def _get_cached_categories(slugs: list[str]) -> dict[str, str | None]:
    """Look up cached market_slug → category_path mappings."""
    if not slugs:
        return {}
    db = await get_db()
    placeholders = ",".join("?" for _ in slugs)
    rows = await db.execute_fetchall(
        f"SELECT market_slug, category_path FROM market_category_map WHERE market_slug IN ({placeholders})",
        slugs,
    )
    return {r[0]: r[1] for r in rows}


async def _save_market_mapping(
    slug: str,
    category_path: str | None,
    tags: list[str],
    question: str | None = None,
    event_id: str | None = None,
    volume: float | None = None,
):
    db = await get_db()
    async with _write_lock:
        await db.execute(
            """INSERT OR REPLACE INTO market_category_map
               (market_slug, category_path, tags, question, event_id, volume, mapped_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (slug, category_path, json.dumps(tags), question, event_id, volume, time.time()),
        )
        await db.commit()


async def _resolve_single_slug(
    client: httpx.AsyncClient, slug: str
) -> tuple[str, str | None]:
    """Fetch a single market by slug from Gamma API and return (slug, category_path)."""
    try:
        resp = await client.get(
            f"{settings.gamma_api_url}/markets",
            params={"slug": slug, "limit": 1},
        )
        resp.raise_for_status()
        markets = resp.json()
        if not markets:
            # Cache as NULL to avoid repeated lookups
            await _save_market_mapping(slug, None, [])
            return slug, None

        mkt = markets[0]
        tags_raw = mkt.get("tags", [])
        tag_slugs = []
        if isinstance(tags_raw, list):
            tag_slugs = [
                t.get("slug", "") if isinstance(t, dict) else str(t) for t in tags_raw
            ]

        category = match_category(tag_slugs)
        question = mkt.get("question")
        event_id = str(mkt.get("event_id", "") or mkt.get("eventId", ""))
        volume = None
        try:
            volume = float(mkt.get("volume", 0))
        except (ValueError, TypeError):
            pass

        await _save_market_mapping(slug, category, tag_slugs, question, event_id, volume)
        return slug, category

    except Exception as e:
        logger.debug(f"Failed to resolve slug '{slug}': {e}")
        # Cache as NULL so we don't retry
        await _save_market_mapping(slug, None, [])
        return slug, None


async def batch_resolve_market_categories(slugs: list[str]) -> dict[str, str | None]:
    """Resolve a batch of market slugs to category paths.

    Checks SQLite cache first, then fetches uncached slugs from Gamma API.
    """
    if not slugs:
        return {}

    unique_slugs = list(set(slugs))
    cached = await _get_cached_categories(unique_slugs)
    uncached = [s for s in unique_slugs if s not in cached]

    if not uncached:
        return cached

    logger.info(f"Resolving {len(uncached)} uncached market slugs from Gamma API...")

    result = dict(cached)
    sem = asyncio.Semaphore(10)

    async def _resolve_with_sem(client: httpx.AsyncClient, slug: str):
        async with sem:
            return await _resolve_single_slug(client, slug)

    async with httpx.AsyncClient(**_client_kwargs()) as client:
        tasks = [_resolve_with_sem(client, s) for s in uncached]
        resolved = await asyncio.gather(*tasks, return_exceptions=True)

    for item in resolved:
        if isinstance(item, tuple):
            result[item[0]] = item[1]

    logger.info(f"Resolved {len(uncached)} slugs. Cache total: {len(result)}")
    return result


# ---------------------------------------------------------------------------
# Hierarchical aggregation helpers
# ---------------------------------------------------------------------------


def _ancestor_paths(category_path: str) -> list[str]:
    """Return all ancestor paths including self.

    E.g. "sports.soccer.epl" → ["sports", "sports.soccer", "sports.soccer.epl"]
    """
    parts = category_path.split(".")
    paths = []
    for i in range(1, len(parts) + 1):
        paths.append(".".join(parts[:i]))
    return paths


# ---------------------------------------------------------------------------
# Full sync
# ---------------------------------------------------------------------------


async def sync_category_leaderboard(top_n: int = 200) -> dict:
    """Sync category leaderboard: fetch top traders, their positions, resolve categories, aggregate."""
    global _last_sync_time

    logger.info(f"Starting category leaderboard sync (top_n={top_n})...")
    t0 = time.time()

    # 1. Get global top traders
    try:
        entries = await lb_svc.get_leaderboard(limit=top_n, offset=0)
    except Exception as e:
        logger.error(f"Failed to fetch leaderboard: {e}")
        return {"error": str(e)}

    if not entries:
        logger.warning("Leaderboard returned 0 entries.")
        return {"traders": 0, "positions": 0, "categories": 0}

    logger.info(f"Fetched {len(entries)} traders from leaderboard.")

    # 2. Fetch positions for each trader (with concurrency limit)
    sem = asyncio.Semaphore(5)
    trader_positions: dict[str, list] = {}  # address → raw positions
    trader_names: dict[str, str | None] = {}

    async def _fetch_positions(entry):
        async with sem:
            try:
                positions = await lb_svc.get_trader_positions(entry.address)
                trader_positions[entry.address] = positions
                trader_names[entry.address] = entry.display_name
            except Exception as e:
                logger.debug(f"Failed to fetch positions for {entry.address[:10]}: {e}")
                trader_positions[entry.address] = []
                trader_names[entry.address] = entry.display_name

    await asyncio.gather(*[_fetch_positions(e) for e in entries])

    total_positions = sum(len(p) for p in trader_positions.values())
    logger.info(f"Fetched {total_positions} positions across {len(entries)} traders.")

    # 3. Collect all unique market slugs
    all_slugs: set[str] = set()
    for positions in trader_positions.values():
        for p in positions:
            slug = p.market_slug
            if slug:
                all_slugs.add(slug)

    logger.info(f"Found {len(all_slugs)} unique market slugs.")

    # 4. Resolve market slugs → categories
    slug_to_category = await batch_resolve_market_categories(list(all_slugs))

    # 5. Aggregate per (trader, category)
    # key = (address, category_path) → stats dict
    agg: dict[tuple[str, str], dict] = {}
    position_rows: list[tuple] = []
    now = time.time()

    for address, positions in trader_positions.items():
        for p in positions:
            slug = p.market_slug
            if not slug:
                continue

            cat = slug_to_category.get(slug)
            if not cat:
                continue

            pnl_val = 0.0
            try:
                pnl_val = float(p.pnl) if p.pnl else 0.0
            except (ValueError, TypeError):
                pass

            is_win = pnl_val > 0

            # Hierarchical: aggregate into self + all ancestors
            for cat_path in _ancestor_paths(cat):
                key = (address, cat_path)
                if key not in agg:
                    agg[key] = {
                        "positions": 0,
                        "pnl": 0.0,
                        "volume": 0.0,
                        "wins": 0,
                        "best_pnl": None,
                        "best_pnl_market": None,
                    }
                a = agg[key]
                a["positions"] += 1
                a["pnl"] += pnl_val
                if is_win:
                    a["wins"] += 1
                if a["best_pnl"] is None or pnl_val > a["best_pnl"]:
                    a["best_pnl"] = pnl_val
                    a["best_pnl_market"] = p.question

            # Position row (only for the deepest category)
            position_rows.append((
                address,
                cat,
                slug,
                p.question,
                p.outcome,
                p.token_id,
                p.size,
                p.avg_price,
                p.current_price,
                p.pnl,
                p.pnl_percent,
                now,
            ))

    # 6. Write to SQLite (full rebuild)
    lb_rows: list[tuple] = []
    for (address, cat_path), stats in agg.items():
        total_pos = stats["positions"]
        win_rate = stats["wins"] / total_pos if total_pos > 0 else None
        lb_rows.append((
            address,
            cat_path,
            trader_names.get(address),
            total_pos,
            stats["pnl"],
            stats["volume"],
            win_rate,
            stats["best_pnl_market"],
            stats["best_pnl"],
            now,
        ))

    db = await get_db()
    async with _write_lock:
        await db.execute("DELETE FROM category_leaderboard")
        await db.execute("DELETE FROM trader_category_positions")

        if lb_rows:
            await db.executemany(
                """INSERT INTO category_leaderboard
                   (address, category_path, display_name, total_positions, total_pnl,
                    total_volume, win_rate, best_pnl_market, best_pnl_value, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                lb_rows,
            )
        if position_rows:
            await db.executemany(
                """INSERT INTO trader_category_positions
                   (address, category_path, market_slug, question, outcome, token_id,
                    size, avg_price, current_price, pnl, pnl_percent, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                position_rows,
            )
        await db.commit()

    elapsed = time.time() - t0
    unique_cats = len(set(cat for _, cat in agg.keys()))
    _last_sync_time = time.time()

    logger.info(
        f"Category leaderboard sync complete: {len(entries)} traders, "
        f"{total_positions} positions, {unique_cats} categories, "
        f"{len(lb_rows)} leaderboard entries, {len(position_rows)} position rows. "
        f"Took {elapsed:.1f}s."
    )

    return {
        "traders": len(entries),
        "positions": total_positions,
        "categories": unique_cats,
        "leaderboard_entries": len(lb_rows),
        "position_rows": len(position_rows),
        "elapsed_seconds": round(elapsed, 1),
    }


# ---------------------------------------------------------------------------
# Query functions (instant, from SQLite)
# ---------------------------------------------------------------------------


async def get_category_leaderboard(
    category_path: str,
    sort_by: str = "pnl",
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], dict]:
    """Query category leaderboard from SQLite.

    Returns (entries, meta) where meta has total_count and last_synced.
    """
    sort_col_map = {
        "pnl": "total_pnl DESC",
        "volume": "total_volume DESC",
        "positions": "total_positions DESC",
        "win_rate": "win_rate DESC",
    }
    order = sort_col_map.get(sort_by, "total_pnl DESC")

    db = await get_db()

    # Total count
    row = await db.execute_fetchall(
        "SELECT COUNT(*) FROM category_leaderboard WHERE category_path = ?",
        (category_path,),
    )
    total_count = row[0][0] if row else 0

    # Last synced
    row = await db.execute_fetchall(
        "SELECT MAX(synced_at) FROM category_leaderboard WHERE category_path = ?",
        (category_path,),
    )
    last_synced = row[0][0] if row and row[0][0] else None

    # Entries
    cursor = await db.execute(
        f"""SELECT address, display_name, total_positions, total_pnl,
                   total_volume, win_rate, best_pnl_market, best_pnl_value
            FROM category_leaderboard
            WHERE category_path = ?
            ORDER BY {order}
            LIMIT ? OFFSET ?""",
        (category_path, limit, offset),
    )
    rows = await cursor.fetchall()
    cols = [col[0] for col in cursor.description]

    entries = []
    for i, row_tuple in enumerate(rows):
        r = dict(zip(cols, row_tuple))
        entries.append({
            "rank": offset + i + 1,
            "address": r["address"],
            "display_name": r["display_name"],
            "total_positions": r["total_positions"],
            "total_pnl": r["total_pnl"],
            "total_volume": r["total_volume"],
            "win_rate": round(r["win_rate"], 4) if r["win_rate"] is not None else None,
            "best_pnl_market": r["best_pnl_market"],
            "best_pnl_value": r["best_pnl_value"],
        })

    meta = {
        "total_count": total_count,
        "last_synced": last_synced,
        "category_path": category_path,
    }
    return entries, meta


async def get_trader_category_profile(
    address: str, category_path: str | None = None
) -> dict:
    """Get a trader's per-category breakdown.

    If category_path is None, returns all categories this trader has data for.
    If category_path is set, returns that category's stats + position list.
    """
    db = await get_db()

    if category_path:
        cursor = await db.execute(
            """SELECT category_path, total_positions, total_pnl, total_volume,
                      win_rate, best_pnl_market, best_pnl_value, display_name
               FROM category_leaderboard
               WHERE address = ? AND category_path = ?""",
            (address, category_path),
        )
    else:
        cursor = await db.execute(
            """SELECT category_path, total_positions, total_pnl, total_volume,
                      win_rate, best_pnl_market, best_pnl_value, display_name
               FROM category_leaderboard
               WHERE address = ?
               ORDER BY total_pnl DESC""",
            (address,),
        )
    rows = await cursor.fetchall()
    cols = [col[0] for col in cursor.description]

    display_name = None
    categories = []
    for row_tuple in rows:
        r = dict(zip(cols, row_tuple))
        if not display_name:
            display_name = r["display_name"]
        categories.append({
            "category_path": r["category_path"],
            "total_positions": r["total_positions"],
            "total_pnl": r["total_pnl"],
            "total_volume": r["total_volume"],
            "win_rate": round(r["win_rate"], 4) if r["win_rate"] is not None else None,
            "best_pnl_market": r["best_pnl_market"],
            "best_pnl_value": r["best_pnl_value"],
        })

    result: dict = {
        "address": address,
        "display_name": display_name,
        "categories": categories,
    }

    # If specific category, also return positions
    if category_path:
        pos_rows = await _get_trader_positions(address, category_path)
        result["positions"] = pos_rows

    return result


async def _get_trader_positions(address: str, category_path: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        """SELECT market_slug, question, outcome, token_id, size,
                  avg_price, current_price, pnl, pnl_percent
           FROM trader_category_positions
           WHERE address = ? AND category_path = ?
           ORDER BY CAST(pnl AS REAL) DESC""",
        (address, category_path),
    )
    rows = await cursor.fetchall()
    cols = [col[0] for col in cursor.description]
    return [dict(zip(cols, row)) for row in rows]


async def get_category_stats(category_path: str) -> dict:
    """Aggregate stats for a category: total traders, volume, avg PnL, best/worst."""
    db = await get_db()
    row = await db.execute_fetchall(
        """SELECT COUNT(*), SUM(total_volume), AVG(total_pnl),
                  MAX(total_pnl), MIN(total_pnl)
           FROM category_leaderboard
           WHERE category_path = ?""",
        (category_path,),
    )

    if not row or row[0][0] == 0:
        return {
            "category_path": category_path,
            "total_traders": 0,
            "total_volume": 0,
            "avg_pnl": 0,
            "best_trader_address": None,
            "best_trader_pnl": None,
            "worst_trader_pnl": None,
        }

    total_traders, total_volume, avg_pnl, best_pnl, worst_pnl = row[0]

    # Get best and worst trader addresses
    best_row = await db.execute_fetchall(
        "SELECT address FROM category_leaderboard WHERE category_path = ? ORDER BY total_pnl DESC LIMIT 1",
        (category_path,),
    )
    worst_row = await db.execute_fetchall(
        "SELECT address FROM category_leaderboard WHERE category_path = ? ORDER BY total_pnl ASC LIMIT 1",
        (category_path,),
    )

    return {
        "category_path": category_path,
        "total_traders": total_traders,
        "total_volume": round(total_volume or 0, 2),
        "avg_pnl": round(avg_pnl or 0, 2),
        "best_trader_address": best_row[0][0] if best_row else None,
        "best_trader_pnl": round(best_pnl, 2) if best_pnl is not None else None,
        "worst_trader_address": worst_row[0][0] if worst_row else None,
        "worst_trader_pnl": round(worst_pnl, 2) if worst_pnl is not None else None,
    }


def can_sync() -> bool:
    """Check if enough time has passed since the last sync."""
    return (time.time() - _last_sync_time) >= SYNC_COOLDOWN


async def get_sync_status() -> dict:
    """Return current sync status info."""
    db = await get_db()
    row = await db.execute_fetchall("SELECT COUNT(*) FROM category_leaderboard")
    lb_count = row[0][0] if row else 0

    row = await db.execute_fetchall("SELECT COUNT(*) FROM trader_category_positions")
    pos_count = row[0][0] if row else 0

    row = await db.execute_fetchall("SELECT COUNT(*) FROM market_category_map")
    map_count = row[0][0] if row else 0

    row = await db.execute_fetchall("SELECT MAX(synced_at) FROM category_leaderboard")
    last_synced = row[0][0] if row and row[0][0] else None

    return {
        "leaderboard_entries": lb_count,
        "position_snapshots": pos_count,
        "market_mappings_cached": map_count,
        "last_synced": last_synced,
    }
