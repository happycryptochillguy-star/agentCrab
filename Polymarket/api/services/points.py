"""Points calculation service for $CRAB token airdrop.

Points are computed directly from existing balances data — no separate
accumulation needed.  Formula:
    deposit_points = total_deposited_wei // payment_amount_wei
    usage_points   = total_consumed_wei  // payment_amount_wei
    total_points   = deposit_points + usage_points

1 USDT deposited  = 100 points  (100 × 0.01 USDT units)
1 API call used   = 1 point     (0.01 USDT consumed)
"""

import time

from api.config import settings
from api.services.balance import get_db, _write_lock

UNIT = settings.payment_amount_wei  # 10^16 = 0.01 USDT


async def get_points(wallet_address: str) -> dict:
    """Calculate points for a single wallet.

    Returns dict with deposit_points, usage_points, bonus_points,
    total_points, and the underlying USDT values.
    """
    addr = wallet_address.lower()
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT total_deposited, total_consumed FROM balances WHERE wallet_address = ?",
        (addr,),
    )
    if not rows:
        return {
            "wallet_address": addr,
            "deposit_points": 0,
            "usage_points": 0,
            "bonus_points": 0,
            "total_points": 0,
            "total_deposited_usdt": 0.0,
            "total_consumed_usdt": 0.0,
        }

    total_deposited, total_consumed = rows[0]
    deposit_points = total_deposited // UNIT
    usage_points = total_consumed // UNIT

    return {
        "wallet_address": addr,
        "deposit_points": deposit_points,
        "usage_points": usage_points,
        "bonus_points": 0,
        "total_points": deposit_points + usage_points,
        "total_deposited_usdt": round(total_deposited / 10**18, 4),
        "total_consumed_usdt": round(total_consumed / 10**18, 4),
    }


async def get_leaderboard(limit: int = 20, offset: int = 0) -> list[dict]:
    """Return the top wallets ranked by total points (descending).

    Each entry: {rank, wallet_address, deposit_points, usage_points, total_points}.
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    db = await get_db()
    rows = await db.execute_fetchall(
        """
        SELECT wallet_address, total_deposited, total_consumed
        FROM balances
        ORDER BY (total_deposited + total_consumed) DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )

    result = []
    for i, (addr, deposited, consumed) in enumerate(rows):
        dep = deposited // UNIT
        use = consumed // UNIT
        result.append({
            "rank": offset + i + 1,
            "wallet_address": addr,
            "deposit_points": dep,
            "usage_points": use,
            "total_points": dep + use,
        })
    return result


async def get_total_stats() -> dict:
    """Aggregate stats across all users."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT COUNT(*), COALESCE(SUM(total_deposited), 0), COALESCE(SUM(total_consumed), 0) FROM balances"
    )
    count, total_dep, total_con = rows[0]
    return {
        "total_users": count,
        "total_deposit_points": total_dep // UNIT,
        "total_usage_points": total_con // UNIT,
        "total_points": (total_dep + total_con) // UNIT,
        "total_deposited_usdt": round(total_dep / 10**18, 4),
        "total_consumed_usdt": round(total_con / 10**18, 4),
    }


async def take_snapshot(snapshot_name: str) -> int:
    """Snapshot current points for all wallets into points_snapshot table.

    Returns the number of wallets captured.
    """
    db = await get_db()
    now = time.time()

    rows = await db.execute_fetchall(
        "SELECT wallet_address, total_deposited, total_consumed FROM balances"
    )

    async with _write_lock:
        for addr, deposited, consumed in rows:
            dep = deposited // UNIT
            use = consumed // UNIT
            await db.execute(
                """INSERT INTO points_snapshot
                   (wallet_address, deposit_points, usage_points, bonus_points, total_points, snapshot_at, snapshot_name)
                   VALUES (?, ?, ?, 0, ?, ?, ?)""",
                (addr, dep, use, dep + use, now, snapshot_name),
            )
        await db.commit()

    return len(rows)
