import asyncio
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.config import settings
from api.services.balance import init_db
from api.services.payment import deposit_scanner_loop
from api.routes import football, payment

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("agentway")


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
    # Startup
    logger.info("Initializing database...")
    await init_db()

    # Start background deposit scanner (only if contract is configured)
    scanner_task = None
    if settings.contract_address:
        logger.info("Starting deposit scanner (interval: %ds)...", settings.scanner_interval_seconds)
        scanner_task = asyncio.create_task(deposit_scanner_loop())
    else:
        logger.warning("CONTRACT_ADDRESS not set — deposit scanner disabled")

    yield

    # Shutdown
    if scanner_task:
        scanner_task.cancel()
        try:
            await scanner_task
        except asyncio.CancelledError:
            pass
    logger.info("Shutdown complete")


app = FastAPI(
    title="agentWay - Polymarket Middleware",
    description="AI-agent-friendly API for Polymarket football/soccer markets. Paid via USDT on BSC.",
    version="0.1.0",
    lifespan=lifespan,
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


app.include_router(football.router)
app.include_router(payment.router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "summary": "agentWay Polymarket API is running.",
        "data": {
            "contract_address": settings.contract_address or "not configured",
            "payment_amount": "0.01 USDT per call",
            "chain": "BSC (Chain ID: 56)",
        },
    }
