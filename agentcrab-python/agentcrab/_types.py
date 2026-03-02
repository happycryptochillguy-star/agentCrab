"""Response dataclasses with .raw escape hatch for full server response."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Balance:
    """Prepaid balance on agentCrab."""
    wallet_address: str
    remaining_wei: str
    calls_remaining: int
    total_deposited_wei: str = ""
    total_consumed_wei: str = ""
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
    raw: dict = field(default_factory=dict, repr=False)


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
    api_key: str
    secret: str
    passphrase: str
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


def _safe_get(d: dict, key: str, default: Any = None) -> Any:
    """Get a value from a dict, returning default if missing or None."""
    v = d.get(key)
    return v if v is not None else default
