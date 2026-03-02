"""agentcrab — Python SDK for the agentCrab Polymarket API."""

__version__ = "0.1.0"

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
    Balance,
    BatchOrderResult,
    DepositResult,
    Market,
    Orderbook,
    OrderResult,
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
    "Balance",
    "BatchOrderResult",
    "DepositResult",
    "Market",
    "Orderbook",
    "OrderResult",
    "Position",
    "Price",
    "SetupResult",
    "Trade",
    "Trigger",
    "TriggerResult",
]
