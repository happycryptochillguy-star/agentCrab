import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.config import settings
from api.services.balance import init_db
from api.services.payment import deposit_scanner_loop
from api.routes import football, payment

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("agentway")


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
