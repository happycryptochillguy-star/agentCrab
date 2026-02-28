from pydantic import BaseModel


# === API Response Wrappers ===

class SuccessResponse(BaseModel):
    status: str = "ok"
    summary: str
    data: dict | list | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    error_code: str
    message: str


# === Polymarket Models ===

class MarketOutcome(BaseModel):
    outcome: str
    price: float | None = None
    token_id: str | None = None


class Market(BaseModel):
    question: str
    market_slug: str | None = None
    outcomes: list[MarketOutcome]
    volume: float | None = None
    liquidity: float | None = None
    end_date: str | None = None
    active: bool = True


class FootballEvent(BaseModel):
    event_id: str
    title: str
    slug: str | None = None
    markets: list[Market]
    volume: float | None = None
    start_date: str | None = None
    end_date: str | None = None


# === Payment Models ===

class BalanceResponse(BaseModel):
    wallet_address: str
    total_deposited_wei: str
    total_consumed_wei: str
    remaining_wei: str
    calls_remaining: int


class VerifyResponse(BaseModel):
    tx_hash: str
    verified: bool
    wallet_address: str | None = None
    message: str
