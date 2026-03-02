"""Health probe service — periodic checks on all external dependencies + Telegram alerts.

Probes 7 external services every 15 minutes:
  - Gamma API (markets)
  - Data API (leaderboard/positions)
  - CLOB API (trading)
  - fun.xyz (deposit relay)
  - Polymarket Relayer (gasless ops)
  - BSC RPC
  - Polygon RPC

On state change (ok→fail after 2 consecutive failures): sends Telegram DOWN alert.
On recovery (fail→ok): sends Telegram RECOVERY alert.
Re-alerts every 2h if still down.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass

from api.config import settings
from api.services.http_pool import get_proxy_client, get_direct_client, get_telegram_client

logger = logging.getLogger("agentcrab.health")

PROBE_INTERVAL = 15 * 60  # 15 minutes
ALERT_REPEAT_INTERVAL = 2 * 3600  # re-alert every 2h if still down
FAILURE_THRESHOLD = 2  # consecutive failures before alerting


@dataclass
class ProbeState:
    name: str
    label: str
    status: str = "unknown"  # "ok", "fail", "unknown"
    last_check: float = 0
    last_ok: float | None = None
    last_fail: float | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    alerted_at: float | None = None


_states: dict[str, ProbeState] = {}


# ---------------------------------------------------------------------------
# Probe functions — each returns (ok: bool, detail: str)
# ---------------------------------------------------------------------------

async def _probe_gamma() -> tuple[bool, str]:
    c = get_proxy_client()
    resp = await c.get(
        f"{settings.gamma_api_url}/events",
        params={"limit": 1, "active": "true"},
    )
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return False, "Empty response"
    return True, f"OK ({len(data)} events)"


async def _probe_data_api() -> tuple[bool, str]:
    c = get_proxy_client()
    resp = await c.get(
        f"{settings.data_api_url}/v1/leaderboard",
        params={"category": "OVERALL", "timePeriod": "ALL", "orderBy": "PNL", "limit": 1},
    )
    resp.raise_for_status()
    data = resp.json()
    return True, f"OK ({len(data)} entries)"


async def _probe_clob() -> tuple[bool, str]:
    c = get_proxy_client()
    resp = await c.get(f"{settings.clob_api_url}/time")
    resp.raise_for_status()
    return True, f"OK (server time: {resp.text[:30]})"


async def _probe_fun_xyz() -> tuple[bool, str]:
    if not settings.fun_xyz_api_url:
        return True, "Skipped (not configured)"
    c = get_proxy_client()
    # GET to base URL — any non-5xx means the server is alive
    resp = await c.get(
        settings.fun_xyz_api_url,
        headers={"x-api-key": settings.fun_xyz_api_key} if settings.fun_xyz_api_key else {},
    )
    if resp.status_code < 500:
        return True, f"OK (status {resp.status_code})"
    return False, f"Server error: {resp.status_code}"


async def _probe_relayer() -> tuple[bool, str]:
    if not settings.relayer_url:
        return True, "Skipped (not configured)"
    c = get_proxy_client()
    resp = await c.get(settings.relayer_url)
    if resp.status_code < 500:
        return True, f"OK (status {resp.status_code})"
    return False, f"Server error: {resp.status_code}"


async def _probe_bsc_rpc() -> tuple[bool, str]:
    c = get_direct_client()
    resp = await c.post(
        settings.bsc_rpc_url,
        json={"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
    )
    resp.raise_for_status()
    data = resp.json()
    result = data.get("result", "0x0")
    block = int(result, 16) if isinstance(result, str) else 0
    return True, f"OK (block {block})"


async def _probe_polygon_rpc() -> tuple[bool, str]:
    if not settings.polygon_rpc_url:
        return True, "Skipped (not configured)"
    c = get_direct_client()
    resp = await c.post(
        settings.polygon_rpc_url,
        json={"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
    )
    resp.raise_for_status()
    data = resp.json()
    result = data.get("result", "0x0")
    block = int(result, 16) if isinstance(result, str) else 0
    return True, f"OK (block {block})"


# Probe registry: (name, label, function)
PROBES = [
    ("gamma_api", "Gamma API (markets)", _probe_gamma),
    ("data_api", "Data API (leaderboard/positions)", _probe_data_api),
    ("clob_api", "CLOB API (trading)", _probe_clob),
    ("fun_xyz", "fun.xyz (deposit relay)", _probe_fun_xyz),
    ("relayer", "Polymarket Relayer (gasless ops)", _probe_relayer),
    ("bsc_rpc", "BSC RPC", _probe_bsc_rpc),
    ("polygon_rpc", "Polygon RPC", _probe_polygon_rpc),
]


# ---------------------------------------------------------------------------
# Telegram notification
# ---------------------------------------------------------------------------

async def send_telegram(message: str):
    """Send a plain-text message to the configured Telegram chat."""
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        logger.warning("Telegram not configured, skipping alert")
        return

    try:
        c = get_telegram_client()
        resp = await c.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
        )
        if resp.status_code != 200:
            logger.warning(f"Telegram API returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"Failed to send Telegram alert: {e}")


async def send_bark(title: str, body: str, critical: bool = False):
    """Send a Bark push notification to iOS device."""
    bark_url = settings.bark_url
    if not bark_url:
        return

    try:
        params: dict = {"title": title, "body": body}
        if critical:
            params["level"] = "critical"  # continuous ringing for critical alerts
        c = get_direct_client()
        resp = await c.post(f"{bark_url.rstrip('/')}/push", json=params)
        if resp.status_code != 200:
            logger.warning(f"Bark API returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"Failed to send Bark alert: {e}")


async def _notify(message: str, bark_title: str = "", bark_body: str = "", critical: bool = False):
    """Send both Telegram + Bark notifications in parallel."""
    tasks = [send_telegram(message)]
    if bark_title:
        tasks.append(send_bark(bark_title, bark_body or message, critical=critical))
    await asyncio.gather(*tasks, return_exceptions=True)


# ---------------------------------------------------------------------------
# Run probes + alert logic
# ---------------------------------------------------------------------------

async def run_all_probes() -> dict[str, dict]:
    """Execute all probes, update state, send alerts on state changes.

    Randomizes probe order and adds small delays between probes
    to avoid predictable request patterns.
    """
    results: dict[str, dict] = {}
    now = time.time()

    # Shuffle probe order each run
    probes = list(PROBES)
    random.shuffle(probes)

    for i, (name, label, probe_fn) in enumerate(probes):
        # Random delay between probes (2-8s) to spread requests
        if i > 0:
            await asyncio.sleep(random.uniform(2, 8))
        if name not in _states:
            _states[name] = ProbeState(name=name, label=label)
        state = _states[name]

        try:
            ok, detail = await probe_fn()
        except Exception as e:
            ok = False
            detail = str(e)[:200]

        prev_status = state.status
        state.last_check = now

        if ok:
            state.status = "ok"
            state.last_ok = now
            state.consecutive_failures = 0
            state.consecutive_successes += 1
            state.last_error = None

            # Recovery alert
            if prev_status == "fail" and state.alerted_at:
                downtime = now - state.alerted_at
                mins = int(downtime / 60)
                await _notify(
                    message=(
                        f"[RECOVERED] agentCrab\n\n"
                        f"Service: {label}\n"
                        f"Status: UP (recovered)\n"
                        f"Downtime: ~{mins} min\n"
                        f"Detail: {detail}"
                    ),
                    bark_title="agentCrab Recovered",
                    bark_body=f"{label} is back UP (~{mins}min downtime)",
                )
                state.alerted_at = None

        else:
            state.status = "fail"
            state.last_fail = now
            state.last_error = detail
            state.consecutive_failures += 1
            state.consecutive_successes = 0

            # DOWN alert (after threshold consecutive failures)
            should_alert = False
            if state.consecutive_failures >= FAILURE_THRESHOLD:
                if state.alerted_at is None:
                    should_alert = True
                elif (now - state.alerted_at) >= ALERT_REPEAT_INTERVAL:
                    should_alert = True  # re-alert after 2h

            if should_alert:
                last_ok_str = "never"
                if state.last_ok:
                    mins_ago = int((now - state.last_ok) / 60)
                    last_ok_str = f"~{mins_ago} min ago"

                await _notify(
                    message=(
                        f"[DOWN] agentCrab Health Alert\n\n"
                        f"Service: {label}\n"
                        f"Status: DOWN\n"
                        f"Error: {detail}\n"
                        f"Failures: {state.consecutive_failures} consecutive\n"
                        f"Last OK: {last_ok_str}"
                    ),
                    bark_title="agentCrab DOWN",
                    bark_body=f"{label}: {detail}",
                    critical=True,  # call=1, continuous ringing
                )
                state.alerted_at = now

        results[name] = {
            "label": label,
            "status": state.status,
            "detail": detail,
            "last_check": state.last_check,
            "last_ok": state.last_ok,
            "consecutive_failures": state.consecutive_failures,
        }

        log_level = "OK" if ok else "FAIL"
        logger.info(f"Probe [{name}]: {log_level} — {detail}")

    return results


def get_all_states() -> dict[str, dict]:
    """Return current state of all probes (for admin dashboard)."""
    result = {}
    for name, state in _states.items():
        result[name] = {
            "label": state.label,
            "status": state.status,
            "last_check": state.last_check,
            "last_ok": state.last_ok,
            "last_fail": state.last_fail,
            "last_error": state.last_error,
            "consecutive_failures": state.consecutive_failures,
        }
    return result


async def health_probe_loop():
    """Background loop: run all probes every PROBE_INTERVAL."""
    try:
        # Wait 30s for app to stabilize
        await asyncio.sleep(30)

        logger.info("Running initial health probes...")
        results = await run_all_probes()
        ok_count = sum(1 for r in results.values() if r["status"] == "ok")
        fail_count = sum(1 for r in results.values() if r["status"] == "fail")
        logger.info(f"Initial health check: {ok_count} OK, {fail_count} FAIL")

        # Send startup summary
        lines = ["agentCrab server started. Health check results:\n"]
        for name, r in results.items():
            icon = "[OK]" if r["status"] == "ok" else "[FAIL]"
            lines.append(f"{icon} {r['label']}: {r.get('detail', '')}")
        await _notify(
            message="\n".join(lines),
            bark_title="agentCrab Started",
            bark_body=f"{ok_count} OK, {fail_count} FAIL",
        )

        while True:
            # Jitter: 12-20 min instead of fixed 15 min
            jittered = PROBE_INTERVAL * random.uniform(0.8, 1.35)
            await asyncio.sleep(jittered)
            logger.info("Running periodic health probes...")
            try:
                await run_all_probes()
            except Exception as e:
                logger.error(f"Health probe error: {e}")

    except asyncio.CancelledError:
        logger.info("Health probe loop cancelled (shutdown)")
        raise
    except Exception as e:
        logger.error(f"Health probe loop crashed: {e}")
