"""Trigger service — stop loss / take profit with pre-signed orders.

Agent signs an exit order upfront. Server monitors prices and submits
the pre-signed order when conditions are met.
"""

import asyncio
import json
import logging
import time
import uuid

from api.services.balance import get_db, _write_lock, _encrypt, _decrypt
from api.services import clob as clob_svc

logger = logging.getLogger("agentcrab.triggers")

MONITOR_INTERVAL = 30  # seconds
PRICE_BATCH_SIZE = 20  # max tokens per batch price fetch
MAX_RETRIES = 2  # retries before marking failed


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_trigger(
    wallet_address: str,
    token_id: str,
    trigger_type: str,
    trigger_price: float,
    exit_side: str,
    clob_order: dict,
    signature: str,
    order_type: str,
    l2_api_key: str,
    l2_secret: str,
    l2_passphrase: str,
    size: float | None = None,
    price: float | None = None,
    market_question: str | None = None,
    market_outcome: str | None = None,
    expires_in_hours: float | None = None,
) -> dict:
    """Store a new trigger in SQLite. Returns the trigger record."""
    trigger_id = str(uuid.uuid4())
    now = time.time()
    expires_at = now + expires_in_hours * 3600 if expires_in_hours else None

    db = await get_db()
    async with _write_lock:
        await db.execute(
            """INSERT INTO triggers
               (id, wallet_address, token_id, trigger_type, trigger_price,
                exit_side, clob_order, signature, order_type,
                l2_api_key, l2_secret, l2_passphrase,
                size, price, market_question, market_outcome,
                status, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
            (
                trigger_id,
                wallet_address.lower(),
                token_id,
                trigger_type,
                str(trigger_price),
                exit_side.upper(),
                json.dumps(clob_order),
                signature,
                order_type,
                _encrypt(l2_api_key),
                _encrypt(l2_secret),
                _encrypt(l2_passphrase),
                str(size) if size else None,
                str(price) if price else None,
                market_question,
                market_outcome,
                now,
                expires_at,
            ),
        )
        await db.commit()

    return {
        "trigger_id": trigger_id,
        "status": "active",
        "token_id": token_id,
        "trigger_type": trigger_type,
        "trigger_price": str(trigger_price),
        "exit_side": exit_side.upper(),
        "size": str(size) if size else None,
        "price": str(price) if price else None,
        "market_question": market_question,
        "market_outcome": market_outcome,
        "created_at": now,
        "expires_at": expires_at,
    }


async def get_trigger(trigger_id: str, wallet_address: str | None = None) -> dict | None:
    """Get a single trigger by ID. Optionally filter by wallet."""
    db = await get_db()
    db.row_factory = _row_factory
    if wallet_address:
        row = await db.execute_fetchall(
            "SELECT * FROM triggers WHERE id = ? AND wallet_address = ?",
            (trigger_id, wallet_address.lower()),
        )
    else:
        row = await db.execute_fetchall(
            "SELECT * FROM triggers WHERE id = ?",
            (trigger_id,),
        )
    db.row_factory = None
    if not row:
        return None
    return _row_to_dict(row[0])


async def list_triggers(
    wallet_address: str,
    status: str | None = None,
    token_id: str | None = None,
) -> list[dict]:
    """List triggers for a wallet, optionally filtered."""
    query = "SELECT * FROM triggers WHERE wallet_address = ?"
    params: list = [wallet_address.lower()]

    if status:
        query += " AND status = ?"
        params.append(status)
    if token_id:
        query += " AND token_id = ?"
        params.append(token_id)

    query += " ORDER BY created_at DESC"

    db = await get_db()
    db.row_factory = _row_factory
    rows = await db.execute_fetchall(query, params)
    db.row_factory = None
    return [_row_to_dict(r) for r in rows]


async def cancel_trigger(trigger_id: str, wallet_address: str) -> bool:
    """Cancel a single trigger. Returns True if cancelled."""
    db = await get_db()
    async with _write_lock:
        cursor = await db.execute(
            "UPDATE triggers SET status = 'cancelled' WHERE id = ? AND wallet_address = ? AND status = 'active'",
            (trigger_id, wallet_address.lower()),
        )
        await db.commit()
        return cursor.rowcount > 0


async def cancel_all_triggers(
    wallet_address: str,
    token_id: str | None = None,
) -> int:
    """Cancel all active triggers for a wallet. Returns count cancelled."""
    query = "UPDATE triggers SET status = 'cancelled' WHERE wallet_address = ? AND status = 'active'"
    params: list = [wallet_address.lower()]
    if token_id:
        query += " AND token_id = ?"
        params.append(token_id)

    db = await get_db()
    async with _write_lock:
        cursor = await db.execute(query, params)
        await db.commit()
        return cursor.rowcount


# ---------------------------------------------------------------------------
# Monitor loop
# ---------------------------------------------------------------------------


def should_trigger(trigger: dict, current_price: float) -> bool:
    """Evaluate whether a trigger condition is met.

    SELL exit (closing long):
      - stop_loss:   price <= trigger_price  (price dropped)
      - take_profit: price >= trigger_price  (price rose)

    BUY exit (closing short):
      - stop_loss:   price >= trigger_price  (price rose)
      - take_profit: price <= trigger_price  (price dropped)
    """
    tp = float(trigger["trigger_price"])
    exit_side = trigger["exit_side"].upper()
    trigger_type = trigger["trigger_type"]

    if exit_side == "SELL":
        if trigger_type == "stop_loss":
            return current_price <= tp
        else:  # take_profit
            return current_price >= tp
    else:  # BUY
        if trigger_type == "stop_loss":
            return current_price >= tp
        else:  # take_profit
            return current_price <= tp


async def _execute_trigger(trigger: dict) -> dict:
    """Submit the pre-signed order for a triggered trigger."""
    clob_order = json.loads(trigger["clob_order"])
    return await clob_svc.post_signed_order(
        clob_order=clob_order,
        signature=trigger["signature"],
        order_type=trigger["order_type"],
        api_key=_decrypt(trigger["l2_api_key"]),
        secret=_decrypt(trigger["l2_secret"]),
        passphrase=_decrypt(trigger["l2_passphrase"]),
        eoa_address=trigger["wallet_address"],
    )


async def _update_trigger_status(
    trigger_id: str,
    status: str,
    result_order_id: str | None = None,
    result_status: str | None = None,
    result_error: str | None = None,
):
    """Update trigger status after execution attempt."""
    now = time.time()
    db = await get_db()
    async with _write_lock:
        await db.execute(
            """UPDATE triggers SET status = ?, triggered_at = ?, submitted_at = ?,
               result_order_id = ?, result_status = ?, result_error = ?
               WHERE id = ?""",
            (status, now, now, result_order_id, result_status, result_error, trigger_id),
        )
        await db.commit()


async def _get_active_triggers() -> list[dict]:
    """Fetch all active triggers from SQLite."""
    db = await get_db()
    db.row_factory = _row_factory
    rows = await db.execute_fetchall(
        "SELECT * FROM triggers WHERE status = 'active'"
    )
    db.row_factory = None
    return [dict(r) for r in rows]


async def _expire_old_triggers():
    """Mark expired triggers."""
    now = time.time()
    db = await get_db()
    async with _write_lock:
        cursor = await db.execute(
            "UPDATE triggers SET status = 'expired' WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at < ?",
            (now,),
        )
        if cursor.rowcount > 0:
            logger.info("Expired %d trigger(s)", cursor.rowcount)
        await db.commit()


async def _notify_trigger_event(trigger: dict, event: str, detail: str = ""):
    """Send Telegram notification for trigger events."""
    try:
        from api.services.health import send_telegram

        market = trigger.get("market_question", trigger["token_id"][:16])
        msg = (
            f"[TRIGGER {event}] agentCrab\n\n"
            f"Type: {trigger['trigger_type']}\n"
            f"Market: {market}\n"
            f"Trigger Price: {trigger['trigger_price']}\n"
            f"Side: {trigger['exit_side']}\n"
        )
        if detail:
            msg += f"Detail: {detail}\n"
        await send_telegram(msg)
    except Exception:
        pass  # Don't let notification failure break the loop


async def trigger_monitor_loop():
    """Background loop: check prices and execute triggers every MONITOR_INTERVAL seconds."""
    try:
        # Wait for app to stabilize
        await asyncio.sleep(10)
        logger.info("Trigger monitor loop started (interval: %ds)", MONITOR_INTERVAL)

        while True:
            try:
                # Expire old triggers first
                await _expire_old_triggers()

                # Get active triggers
                triggers = await _get_active_triggers()
                if not triggers:
                    await asyncio.sleep(MONITOR_INTERVAL)
                    continue

                # Collect unique token_ids
                token_ids = list({t["token_id"] for t in triggers})
                logger.info(
                    "Monitoring %d trigger(s) across %d token(s)",
                    len(triggers), len(token_ids),
                )

                # Batch fetch prices
                prices: dict[str, float] = {}
                for i in range(0, len(token_ids), PRICE_BATCH_SIZE):
                    batch = token_ids[i : i + PRICE_BATCH_SIZE]
                    try:
                        summaries = await clob_svc.get_prices_batch(batch)
                        for ps in summaries:
                            mid = ps.midpoint
                            if mid:
                                prices[ps.token_id] = float(mid)
                    except Exception as e:
                        logger.warning("Price fetch failed for batch: %s", e)

                # Evaluate each trigger
                for trigger in triggers:
                    tid = trigger["token_id"]
                    if tid not in prices:
                        continue

                    current_price = prices[tid]
                    if not should_trigger(trigger, current_price):
                        continue

                    # Trigger condition met — execute
                    logger.info(
                        "Trigger %s fired: %s %s @ price %.4f (trigger: %s)",
                        trigger["id"][:8],
                        trigger["trigger_type"],
                        trigger["exit_side"],
                        current_price,
                        trigger["trigger_price"],
                    )

                    success = False
                    last_error = ""
                    for attempt in range(MAX_RETRIES + 1):
                        try:
                            result = await _execute_trigger(trigger)
                            order_id = result.get("orderID", result.get("id", ""))
                            status = result.get("status", "unknown")
                            await _update_trigger_status(
                                trigger["id"],
                                status="triggered",
                                result_order_id=order_id,
                                result_status=status,
                            )
                            await _notify_trigger_event(
                                trigger, "EXECUTED",
                                f"Order {order_id[:16]}... status: {status}",
                            )
                            success = True
                            break
                        except Exception as e:
                            last_error = str(e)
                            logger.warning(
                                "Trigger %s attempt %d failed: %s",
                                trigger["id"][:8], attempt + 1, e,
                            )
                            if attempt < MAX_RETRIES:
                                await asyncio.sleep(2)

                    if not success:
                        await _update_trigger_status(
                            trigger["id"],
                            status="failed",
                            result_error=last_error,
                        )
                        await _notify_trigger_event(
                            trigger, "FAILED", last_error[:200],
                        )

            except Exception as e:
                logger.error("Trigger monitor error: %s", e)

            await asyncio.sleep(MONITOR_INTERVAL)

    except asyncio.CancelledError:
        logger.info("Trigger monitor loop cancelled (shutdown)")
        raise
    except Exception as e:
        logger.error("Trigger monitor loop crashed: %s", e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_factory(cursor, row):
    """SQLite row factory that returns Row-like objects."""
    cols = [col[0] for col in cursor.description]
    return dict(zip(cols, row))


def _row_to_dict(row) -> dict:
    """Convert a Row to a sanitized dict (strip L2 creds and signature)."""
    d = dict(row) if not isinstance(row, dict) else row
    # Never expose sensitive fields
    for key in ("l2_api_key", "l2_secret", "l2_passphrase", "signature", "clob_order"):
        d.pop(key, None)
    return d
