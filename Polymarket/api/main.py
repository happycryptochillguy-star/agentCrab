import asyncio
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import settings
from api.services.balance import init_db
from api.services import history as history_svc
from api.services import http_pool
from api.routes import agent, payment, deposit, markets, orderbook, positions, traders, trading, category_leaderboard
from api.routes import admin as admin_routes
from api.routes import triggers as triggers_routes
from api.services import category_leaderboard as cat_lb_svc
from api.services import health as health_svc
from api.services import triggers as trigger_svc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("agentcrab")


# === Tiered Rate Limiter ===
#
# Different limits for different endpoint tiers to prevent free-endpoint DDoS
# from affecting paid users. Also per-wallet limiting for auth'd endpoints.
#
# Tier 0 (open):   /health, /agent/capabilities, /markets/categories, /markets/tags,
#                  /trading/setup, /trading/contracts, /deposit/supported-assets
# Tier 1 (free):  /agent/create-wallet  (CPU-heavy key generation)
# Tier 2 (auth):  /payment/*, /trading/prepare-*  (free but authenticated)
# Tier 3 (paid):  everything else  (costs 0.01 USDT, economic protection)
# Tier 4 (admin): /admin/*

RATE_WINDOW = 60  # seconds

# Per-IP limits by tier (requests per RATE_WINDOW)
_TIER_LIMITS = {
    "open": 30,       # public info endpoints
    "keygen": 3,      # create-wallet (CPU heavy)
    "auth": 60,       # free authenticated endpoints
    "paid": 120,      # paid endpoints (economic cost already limits abuse)
    "admin": 10,      # admin endpoints
}

# Path prefix → tier mapping (checked in order, first match wins)
_TIER_RULES: list[tuple[str, str]] = [
    ("/admin/", "admin"),
    ("/polymarket/agent/create-wallet", "keygen"),
    ("/polymarket/agent/", "open"),
    ("/polymarket/markets/categories", "open"),
    ("/polymarket/markets/tags", "open"),
    ("/polymarket/trading/setup", "open"),
    ("/polymarket/trading/contracts", "open"),
    ("/polymarket/deposit/supported-assets", "open"),
    ("/health", "open"),
    # prepare-*, credentials, and trigger query endpoints are free (auth only)
    ("/polymarket/payment/", "auth"),
    ("/polymarket/trading/prepare-", "auth"),
    ("/polymarket/trading/credentials", "auth"),
    ("/polymarket/trading/triggers/prepare", "auth"),
    # everything else is paid
]

# Buckets: key = "tier:ip" → deque of timestamps (bounded by tier limit)
_rate_buckets: dict[str, deque] = {}
_rate_buckets_last_cleanup = time.time()
_CLEANUP_INTERVAL = 300  # clean stale entries every 5 min
_MAX_BUCKET_SIZE = 50000  # emergency cap to prevent OOM


def _get_tier(path: str) -> str:
    """Determine rate limit tier from request path."""
    for prefix, tier in _TIER_RULES:
        if path.startswith(prefix):
            return tier
    return "paid"  # default: paid tier


def _check_rate_limit(client_ip: str, path: str) -> tuple[bool, str, int]:
    """Check rate limit. Returns (allowed, tier, limit).

    Uses deque with maxlen for bounded memory per bucket.
    Also performs periodic cleanup of stale buckets to prevent memory leak.
    """
    global _rate_buckets_last_cleanup
    now = time.time()

    # Periodic cleanup: remove buckets with no recent activity
    if now - _rate_buckets_last_cleanup > _CLEANUP_INTERVAL:
        _rate_buckets_last_cleanup = now
        stale_keys = [
            k for k, dq in _rate_buckets.items()
            if not dq or now - dq[-1] > RATE_WINDOW * 2
        ]
        for k in stale_keys:
            del _rate_buckets[k]
        # Emergency: if still too large, drop oldest half
        if len(_rate_buckets) > _MAX_BUCKET_SIZE:
            to_remove = sorted(_rate_buckets.keys(),
                               key=lambda k: _rate_buckets[k][-1] if _rate_buckets[k] else 0
                               )[:len(_rate_buckets) // 2]
            for k in to_remove:
                del _rate_buckets[k]

    tier = _get_tier(path)
    limit = _TIER_LIMITS.get(tier, 30)
    bucket_key = f"{tier}:{client_ip}"

    if bucket_key not in _rate_buckets:
        _rate_buckets[bucket_key] = deque(maxlen=limit)

    timestamps = _rate_buckets[bucket_key]

    # Prune old entries from left (efficient O(k) for deque)
    while timestamps and now - timestamps[0] >= RATE_WINDOW:
        timestamps.popleft()

    if len(timestamps) >= limit:
        return False, tier, limit

    timestamps.append(now)
    return True, tier, limit


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()

    # Start periodic sync loops
    history_task = asyncio.create_task(_history_sync_loop())
    logger.info("Historical events sync loop started")

    cat_lb_task = asyncio.create_task(_category_leaderboard_sync_loop())
    logger.info("Category leaderboard sync loop started")

    health_task = asyncio.create_task(health_svc.health_probe_loop())
    logger.info("Health probe loop started")

    trigger_task = asyncio.create_task(trigger_svc.trigger_monitor_loop())
    logger.info("Trigger monitor loop started")

    logger.info("Startup complete")
    yield

    # Shutdown: cancel all background loops
    for task in (history_task, cat_lb_task, health_task, trigger_task):
        task.cancel()
    for task in (history_task, cat_lb_task, health_task, trigger_task):
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Close shared HTTP connection pools and DB
    await http_pool.close_all()
    from api.services.balance import close_db
    await close_db()
    logger.info("Shutdown complete")


async def _history_sync_loop():
    """Periodic background loop: full sync on first run if empty, then incremental every 6h."""
    try:
        # First run: full sync if empty, otherwise incremental
        is_empty = await history_svc.is_empty()
        if is_empty:
            logger.info("Historical events table empty — running full sync...")
            count = await history_svc.sync_historical_events(max_pages=0)
        else:
            logger.info("Historical events table has data — running incremental sync...")
            count = await history_svc.sync_historical_events(
                max_pages=history_svc.INCREMENTAL_MAX_PAGES
            )
        logger.info(f"Initial history sync done: {count} events.")

        # Then loop forever: sleep → incremental sync
        while True:
            await asyncio.sleep(history_svc.PERIODIC_SYNC_INTERVAL)
            logger.info("Periodic incremental history sync starting...")
            try:
                count = await history_svc.sync_historical_events(
                    max_pages=history_svc.INCREMENTAL_MAX_PAGES
                )
                logger.info(f"Periodic history sync done: {count} events.")
            except Exception as e:
                logger.error(f"Periodic history sync failed: {e}")

    except asyncio.CancelledError:
        logger.info("History sync loop cancelled (shutdown)")
        raise
    except Exception as e:
        logger.error(f"History sync loop crashed: {e}")


async def _category_leaderboard_sync_loop():
    """Periodic background loop: wait for history sync, then sync category leaderboard every 4h."""
    try:
        # Wait 2 min for history sync to populate some market tags first
        await asyncio.sleep(120)

        logger.info("Starting initial category leaderboard sync...")
        try:
            result = await cat_lb_svc.sync_category_leaderboard()
            logger.info(f"Initial category leaderboard sync done: {result}")
        except Exception as e:
            logger.error(f"Initial category leaderboard sync failed: {e}")

        # Then loop: sleep → sync
        while True:
            await asyncio.sleep(cat_lb_svc.PERIODIC_SYNC_INTERVAL)
            logger.info("Periodic category leaderboard sync starting...")
            try:
                result = await cat_lb_svc.sync_category_leaderboard()
                logger.info(f"Periodic category leaderboard sync done: {result}")
            except Exception as e:
                logger.error(f"Periodic category leaderboard sync failed: {e}")

    except asyncio.CancelledError:
        logger.info("Category leaderboard sync loop cancelled (shutdown)")
        raise
    except Exception as e:
        logger.error(f"Category leaderboard sync loop crashed: {e}")


app = FastAPI(
    title="agentCrab - Polymarket Middleware",
    description="AI-agent-friendly API for Polymarket prediction markets. Paid via USDT on BSC.",
    version="0.1.0",
    lifespan=lifespan,
)


# CORS: No wildcard. This is an API-only service (no browser frontend).
# Only allow requests from our own domain. Agents call via HTTP, not browsers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://agentcrab.ai", "https://api.agentcrab.ai"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Use X-Real-IP (set by nginx) or X-Forwarded-For behind reverse proxy,
    # fall back to direct client IP for local development.
    client_ip = (
        request.headers.get("X-Real-IP")
        or (request.headers.get("X-Forwarded-For", "").split(",")[0].strip())
        or (request.client.host if request.client else "unknown")
    )
    path = request.url.path
    allowed, tier, limit = _check_rate_limit(client_ip, path)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "status": "error",
                "error_code": "RATE_LIMITED",
                "message": f"Too many requests ({tier} tier). Maximum {limit} requests per {RATE_WINDOW}s. Please slow down.",
            },
        )
    response = await call_next(request)
    # SDK version header: tells agents the minimum required SDK version
    response.headers["X-Min-SDK-Version"] = settings.min_sdk_version
    return response


# All Polymarket routes under /polymarket prefix.
# Future products: app.include_router(other_router) with different prefix.
polymarket_router = APIRouter(prefix="/polymarket")
polymarket_router.include_router(agent.router)
polymarket_router.include_router(payment.router)
polymarket_router.include_router(deposit.router)
polymarket_router.include_router(markets.router)
polymarket_router.include_router(orderbook.router)
polymarket_router.include_router(positions.router)
polymarket_router.include_router(traders.router)
polymarket_router.include_router(trading.router)
polymarket_router.include_router(triggers_routes.router)
polymarket_router.include_router(category_leaderboard.router)

app.include_router(polymarket_router)

# Admin routes at root level (not under /polymarket)
app.include_router(admin_routes.router)


@app.get("/health")
async def health():
    """Global health check (root level, not under /polymarket)."""
    return {
        "status": "ok",
        "summary": "agentCrab API is running.",
        "data": {
            "products": {
                "polymarket": {
                    "base_path": "/polymarket",
                    "description": "Polymarket prediction markets middleware",
                    "payment": "0.01 USDT/call on BSC",
                },
            },
        },
    }
