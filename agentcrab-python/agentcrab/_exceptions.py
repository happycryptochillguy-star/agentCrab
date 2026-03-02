"""Typed exception hierarchy for the agentcrab SDK."""


class AgentCrabError(Exception):
    """Base exception for all agentcrab errors."""

    def __init__(self, message: str, error_code: str | None = None, status_code: int | None = None):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(message)


class AuthError(AgentCrabError):
    """Signature verification failed (401)."""


class PaymentError(AgentCrabError):
    """Payment-related error (402)."""


class InsufficientBalance(PaymentError):
    """Prepaid balance too low."""


class APIError(AgentCrabError):
    """Server returned an error response (4xx/5xx)."""


class SetupRequired(AgentCrabError):
    """Trading operation called before setup_trading()."""

    def __init__(self, message: str = "Call setup_trading() first to get L2 credentials."):
        super().__init__(message, error_code="SETUP_REQUIRED")


class OrderError(AgentCrabError):
    """Order placement or cancellation failed."""


class NetworkError(AgentCrabError):
    """HTTP transport failure (timeout, connection refused, etc.)."""
