from pydantic import BaseModel, field_validator, ConfigDict


# === API Response Wrappers ===

class SuccessResponse(BaseModel):
    status: str = "ok"
    summary: str
    data: dict | list | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    error_code: str
    message: str


# === Football Models (legacy) ===

class MarketOutcome(BaseModel):
    outcome: str
    price: float | None = None
    token_id: str | None = None


class Market(BaseModel):
    question: str
    market_slug: str | None = None
    condition_id: str | None = None
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


class PrepareDepositRequest(BaseModel):
    amount_usdt: float  # Amount in USDT (e.g. 1.0 = 100 calls)


class PreparePayRequest(BaseModel):
    pass  # No params needed, always 0.01 USDT


class SubmitTxRequest(BaseModel):
    signed_tx: str | None = None  # Single tx (hex, 0x-prefixed)
    signed_txs: list[str] | None = None  # Batch: broadcast in order
    chain: str = "bsc"  # "bsc" or "polygon"


# === Deposit Models ===

class PreparePolymarketDepositRequest(BaseModel):
    amount_usdt: float  # Amount to deposit to Polymarket


class DepositCreateRequest(BaseModel):
    polymarket_address: str  # User's Polymarket wallet address on Polygon


class DepositAddresses(BaseModel):
    evm: str | None = None  # EVM deposit address (ETH, Polygon, Arbitrum, Base, BSC, etc.)
    svm: str | None = None  # Solana deposit address
    btc: str | None = None  # Bitcoin deposit address


class DepositCreateResponse(BaseModel):
    polymarket_address: str
    deposit_addresses: DepositAddresses
    note: str | None = None


class WithdrawCreateRequest(BaseModel):
    polymarket_address: str  # Source Polymarket wallet on Polygon
    to_chain_id: str  # Destination chain ID (e.g. "56" for BSC, "1" for ETH)
    to_token_address: str  # Destination token contract address
    recipient_address: str  # Destination wallet address


class WithdrawCreateResponse(BaseModel):
    deposit_addresses: DepositAddresses
    note: str | None = None


# === General Market Models ===

class GammaEvent(BaseModel):
    event_id: str
    title: str
    slug: str | None = None
    description: str | None = None
    markets: list[Market]
    volume: float | None = None
    liquidity: float | None = None
    start_date: str | None = None
    end_date: str | None = None
    tags: list[str] | None = None
    image: str | None = None


class GammaMarketDetail(BaseModel):
    market_id: str
    question: str
    description: str | None = None
    market_slug: str | None = None
    condition_id: str | None = None
    outcomes: list[MarketOutcome]
    volume: float | None = None
    liquidity: float | None = None
    end_date: str | None = None
    active: bool = True
    closed: bool = False
    tags: list[str] | None = None
    image: str | None = None


# === Category Models ===

class CategoryInfo(BaseModel):
    id: str
    label: str
    description: str | None = None
    subcategories: list["CategoryInfo"] | None = None


# === Orderbook Models ===

class OrderbookLevel(BaseModel):
    price: str
    size: str


class Orderbook(BaseModel):
    token_id: str
    bids: list[OrderbookLevel]
    asks: list[OrderbookLevel]
    best_bid: str | None = None
    best_ask: str | None = None
    spread: str | None = None
    midpoint: str | None = None


class PriceSummary(BaseModel):
    token_id: str
    best_bid: str | None = None
    best_ask: str | None = None
    midpoint: str | None = None
    spread: str | None = None
    last_trade_price: str | None = None


# === Positions Models ===

class Position(BaseModel):
    market_slug: str | None = None
    question: str | None = None
    outcome: str
    token_id: str
    size: str
    avg_price: str | None = None
    current_price: str | None = None
    pnl: str | None = None
    pnl_percent: str | None = None


class Trade(BaseModel):
    trade_id: str | None = None
    market_slug: str | None = None
    outcome: str | None = None
    side: str
    size: str
    price: str
    timestamp: str | None = None


class Activity(BaseModel):
    type: str  # TRADE, SPLIT, MERGE, REDEEM
    token_id: str | None = None
    amount: str | None = None
    timestamp: str | None = None
    tx_hash: str | None = None


# === Trading Models ===

class SubmitDeploySafeRequest(BaseModel):
    signature: str  # EIP-712 CreateProxy signature (0x-prefixed hex)


class ApprovalData(BaseModel):
    """Strict model for approval_data from prepare-enable. Prevents injection."""
    model_config = ConfigDict(extra="forbid")
    hash: str
    safe_address: str
    nonce: int
    to: str
    data: str
    operation: int
    approvals: list[str]

    @field_validator("to")
    @classmethod
    def validate_to_is_multisend(cls, v: str) -> str:
        # MultiSend address on Polygon — only valid target for approval txs
        if v.lower() != "0xa238cbeb142c10ef7ad8442c6d1f9e89e07e7761":
            raise ValueError("approval_data.to must be the MultiSend contract address")
        return v

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, v: int) -> int:
        if v != 1:  # DelegateCall for MultiSend
            raise ValueError("approval_data.operation must be 1 (DelegateCall)")
        return v


class SubmitApprovalsRequest(BaseModel):
    signature: str  # personal_sign of SafeTx hash (0x-prefixed hex)
    approval_data: ApprovalData


class ClobOrderPayload(BaseModel):
    """Strict model for CLOB order body. Matches Polymarket SDK exactly."""
    model_config = ConfigDict(extra="forbid")
    salt: int
    maker: str
    signer: str
    taker: str
    tokenId: str
    makerAmount: str
    takerAmount: str
    expiration: str
    nonce: str
    feeRateBps: str
    side: str
    signatureType: int

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        if v not in ("BUY", "SELL"):
            raise ValueError("side must be 'BUY' or 'SELL'")
        return v

    @field_validator("signatureType")
    @classmethod
    def validate_sig_type(cls, v: int) -> int:
        if v != 2:  # POLY_GNOSIS_SAFE
            raise ValueError("signatureType must be 2 (POLY_GNOSIS_SAFE)")
        return v


class PrepareOrderRequest(BaseModel):
    token_id: str
    side: str  # BUY or SELL
    size: float
    price: float
    order_type: str = "GTC"  # GTC, GTD, FOK, FAK


class SubmitOrderRequest(BaseModel):
    signature: str  # EIP-712 Order signature (0x-prefixed hex)
    clob_order: ClobOrderPayload
    order_type: str = "GTC"  # GTC, GTD, FOK, FAK


class OrderRequest(BaseModel):
    token_id: str
    side: str  # BUY or SELL
    size: float
    price: float
    order_type: str = "GTC"  # GTC, GTD, FOK, FAK
    expiration: str | None = None  # For GTD orders


class OrderResponse(BaseModel):
    order_id: str
    status: str
    token_id: str
    side: str
    size: str
    price: str
    order_type: str


class CancelRequest(BaseModel):
    order_id: str


class BatchCancelRequest(BaseModel):
    order_ids: list[str] | None = None
    market: str | None = None  # Cancel all orders in a market


# === Leaderboard Models ===

class LeaderboardEntry(BaseModel):
    rank: int
    address: str
    display_name: str | None = None
    volume: str | None = None
    pnl: str | None = None
    positions_count: int | None = None
    trades_count: int | None = None


# === Category Leaderboard Models ===

class CategoryLeaderboardEntry(BaseModel):
    rank: int
    address: str
    display_name: str | None = None
    total_positions: int = 0
    total_pnl: float = 0
    total_volume: float = 0
    win_rate: float | None = None
    best_pnl_market: str | None = None
    best_pnl_value: float | None = None


class TraderCategoryStats(BaseModel):
    category_path: str
    total_positions: int = 0
    total_pnl: float = 0
    total_volume: float = 0
    win_rate: float | None = None
    best_pnl_market: str | None = None
    best_pnl_value: float | None = None


class TraderCategoryProfile(BaseModel):
    address: str
    display_name: str | None = None
    categories: list[TraderCategoryStats]
    positions: list[Position] | None = None


class CategoryStatsResponse(BaseModel):
    category_path: str
    total_traders: int = 0
    total_volume: float = 0
    avg_pnl: float = 0
    best_trader_address: str | None = None
    best_trader_pnl: float | None = None
    worst_trader_pnl: float | None = None


# === Batch Order Models ===

class BatchOrderItem(BaseModel):
    token_id: str
    side: str  # BUY or SELL
    size: float
    price: float
    order_type: str = "GTC"


class PrepareBatchOrderRequest(BaseModel):
    orders: list[BatchOrderItem]  # 1-15 orders


class SubmitBatchOrderItem(BaseModel):
    signature: str  # EIP-712 Order signature (0x-prefixed hex)
    clob_order: ClobOrderPayload
    order_type: str = "GTC"


class SubmitBatchOrderRequest(BaseModel):
    orders: list[SubmitBatchOrderItem]  # 1-15 orders


# === Trigger Models ===

class PrepareTriggerRequest(BaseModel):
    token_id: str
    trigger_type: str  # stop_loss or take_profit
    trigger_price: float
    exit_side: str  # BUY or SELL
    size: float
    exit_price: float
    expires_in_hours: float | None = None  # Optional TTL


class CreateTriggerRequest(BaseModel):
    signature: str  # EIP-712 Order signature
    clob_order: ClobOrderPayload
    order_type: str = "GTC"
    token_id: str
    trigger_type: str  # stop_loss or take_profit
    trigger_price: float
    exit_side: str
    size: float | None = None
    exit_price: float | None = None
    market_question: str | None = None
    market_outcome: str | None = None
    expires_in_hours: float | None = None
