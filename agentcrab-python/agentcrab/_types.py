"""Response dataclasses with .raw escape hatch for full server response."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Balance:
    """Prepaid balance on agentCrab + Polymarket trading balance."""
    wallet_address: str
    calls_remaining: int
    remaining_usdt: float = 0.0
    safe_address: str = ""
    trading_balance_usdc: float = 0.0
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class Market:
    """A Polymarket event with its markets."""
    event_id: str
    title: str
    outcomes: list[dict]
    slug: str | None = None
    volume: float | None = None
    end_date: str | None = None
    tags: list[str] | None = None
    image: str | None = None
    condition_id: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    def find_outcome(self, name: str) -> dict:
        """Find an outcome by name (case-insensitive substring match).

        >>> market.find_outcome("Warriors")
        {"outcome": "Golden State Warriors", "price": 0.05, "token_id": "71321..."}
        """
        name_lower = name.lower()
        for o in self.outcomes:
            if name_lower in o.get("outcome", "").lower():
                return o
        available = [o.get("outcome", "?") for o in self.outcomes]
        raise ValueError(f"No outcome matching '{name}'. Available: {available}")


@dataclass
class Orderbook:
    """Orderbook for a token."""
    token_id: str
    bids: list[dict]
    asks: list[dict]
    best_bid: str | None = None
    best_ask: str | None = None
    spread: str | None = None
    midpoint: str | None = None
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class Price:
    """Price summary for a token."""
    token_id: str
    best_bid: str | None = None
    best_ask: str | None = None
    midpoint: str | None = None
    spread: str | None = None
    last_trade_price: str | None = None
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class Position:
    """A position on Polymarket."""
    token_id: str
    outcome: str
    size: str
    question: str | None = None
    market_slug: str | None = None
    avg_price: str | None = None
    current_price: str | None = None
    pnl: str | None = None
    pnl_percent: str | None = None
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class Trade:
    """A trade on Polymarket."""
    side: str
    size: str
    price: str
    trade_id: str | None = None
    market_slug: str | None = None
    outcome: str | None = None
    timestamp: str | None = None
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class OrderResult:
    """Result of a buy/sell/cancel order."""
    order_id: str
    status: str
    success: bool
    taking_amount: str | None = None
    making_amount: str | None = None
    tx_hash: str | None = None
    polygonscan_url: str | None = None
    error: str | None = None
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class DepositResult:
    """Result of a deposit operation."""
    tx_hashes: list[str]
    summary: str
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class SetupResult:
    """Result of setup_trading()."""
    safe_address: str
    api_key: str = field(repr=False)
    secret: str = field(repr=False)
    passphrase: str = field(repr=False)
    steps_completed: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class BatchOrderResult:
    """Result of a batch order submission."""
    results: list[dict]
    total_charged_usdt: float = 0.0
    success_count: int = 0
    fail_count: int = 0
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class TriggerResult:
    """Result of creating a trigger (stop loss / take profit)."""
    trigger_id: str
    status: str
    token_id: str
    trigger_type: str
    trigger_price: str
    exit_side: str
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class Trigger:
    """A trigger (stop loss / take profit) on the server."""
    trigger_id: str
    token_id: str
    trigger_type: str
    trigger_price: str
    exit_side: str
    status: str
    size: str | None = None
    price: str | None = None
    market_question: str | None = None
    market_outcome: str | None = None
    created_at: float | None = None
    triggered_at: float | None = None
    expires_at: float | None = None
    result_order_id: str | None = None
    result_status: str | None = None
    result_error: str | None = None
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class Activity:
    """An on-chain activity record (trade, split, merge, redemption)."""
    type: str
    amount: str
    timestamp: str | None = None
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class HistoricalEvent:
    """A closed Polymarket event from local history DB."""
    event_id: str
    title: str
    category: str | None = None
    volume: float | None = None
    resolution: str | None = None
    closed_time: str | None = None
    raw: dict = field(default_factory=dict, repr=False)


