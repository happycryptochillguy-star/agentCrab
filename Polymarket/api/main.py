import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import settings
from api.services.balance import init_db
from api.routes import agent, football, payment, deposit, markets, orderbook, positions, traders, trading

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
    logger.info("Startup complete")
    yield
    logger.info("Shutdown complete")


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


app.include_router(agent.router)
app.include_router(football.router)
app.include_router(payment.router)
app.include_router(deposit.router)
app.include_router(markets.router)
app.include_router(orderbook.router)
app.include_router(positions.router)
app.include_router(traders.router)
app.include_router(trading.router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "summary": "agentCrab Polymarket API is running.",
        "data": {
            "contract_address": settings.contract_address or "not configured",
            "payment_amount": "0.01 USDT per call",
            "chain": "BSC (Chain ID: 56)",
        },
    }
