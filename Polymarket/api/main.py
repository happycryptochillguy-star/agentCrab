import asyncio
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import settings
from api.services.balance import init_db
from api.services import history as history_svc
from api.routes import agent, payment, deposit, markets, orderbook, positions, traders, trading, category_leaderboard
from api.routes import admin as admin_routes
from api.services import category_leaderboard as cat_lb_svc
from api.services import health as health_svc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("agentcrab")


# === Simple in-memory rate limiter ===

_rate_limit: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 30  # per window per IP


def _check_rate_limit(client_ip: str) -> bool:
    """Return True if request is allowed, False if rate limited."""
    now = time.time()
    timestamps = _rate_limit[client_ip]
    # Prune old entries
    _rate_limit[client_ip] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limit[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    _rate_limit[client_ip].append(now)
    return True


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

    logger.info("Startup complete")
    yield

    # Shutdown: cancel all background loops
    for task in (history_task, cat_lb_task, health_task):
        task.cancel()
    for task in (history_task, cat_lb_task, health_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
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


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={
                "status": "error",
                "error_code": "RATE_LIMITED",
                "message": f"Too many requests. Maximum {RATE_LIMIT_MAX_REQUESTS} requests per {RATE_LIMIT_WINDOW} seconds. Please slow down.",
            },
        )
    return await call_next(request)


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
