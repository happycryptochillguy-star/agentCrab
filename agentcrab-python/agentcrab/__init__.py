"""agentcrab — Python SDK for the agentCrab Polymarket API."""

__version__ = "0.4.0"

from .client import AgentCrab
from ._exceptions import (
    AgentCrabError,
    APIError,
    AuthError,
    InsufficientBalance,
    NetworkError,
    OrderError,
    PaymentError,
    SetupRequired,
)
from ._types import (
    Activity,
    Balance,
    BatchOrderResult,
    DepositResult,
    HistoricalEvent,
    Market,
    Orderbook,
    OrderResult,
    Points,
    Position,
    Price,
    SetupResult,
    Trade,
    Trigger,
    TriggerResult,
)

__all__ = [
    "AgentCrab",
    # Exceptions
    "AgentCrabError",
    "APIError",
    "AuthError",
    "InsufficientBalance",
    "NetworkError",
    "OrderError",
    "PaymentError",
    "SetupRequired",
    # Types
    "Activity",
    "Balance",
    "BatchOrderResult",
    "DepositResult",
    "HistoricalEvent",
    "Market",
    "Orderbook",
    "OrderResult",
    "Points",
    "Position",
    "Price",
    "SetupResult",
    "Trade",
    "Trigger",
    "TriggerResult",
]
