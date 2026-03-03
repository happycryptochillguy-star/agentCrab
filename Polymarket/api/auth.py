"""Reusable authentication and payment dependency for all paid endpoints."""

from fastapi import Header, HTTPException, Request

from api.config import settings
from api.models import ErrorResponse
from api.services import payment as payment_svc
from api.services import balance as balance_svc


async def verify_auth_and_payment(
    request: Request,
    x_wallet_address: str = Header(..., alias="X-Wallet-Address"),
    x_signature: str = Header(..., alias="X-Signature"),
    x_message: str = Header(..., alias="X-Message"),
    x_payment_mode: str = Header(..., alias="X-Payment-Mode"),
    x_tx_hash: str | None = Header(None, alias="X-Tx-Hash"),
) -> str:
    """Verify authentication signature and process payment.

    Returns the wallet address on success.
    Raises HTTPException on failure.
    """
    # Store payment context on request for upstream-failure refund middleware
    request.state.paid_wallet = None
    request.state.paid_amount = 0

    # 1. Verify signature
    if not payment_svc.verify_signature(x_wallet_address, x_message, x_signature):
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error_code="INVALID_SIGNATURE",
                message="Signature verification failed. Sign the message 'agentcrab:{unix_timestamp}' with your wallet private key (EIP-191 personal_sign). Timestamp must be within 5 minutes.",
            ).model_dump(),
        )

    # 2. Verify payment
    endpoint = request.url.path

    if x_payment_mode == "direct":
        if not x_tx_hash:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error_code="MISSING_TX_HASH",
                    message="X-Tx-Hash header is required for direct payment mode. First call pay() on the contract, then pass the transaction hash.",
                ).model_dump(),
            )
        verified = await payment_svc.verify_direct_payment(x_tx_hash, x_wallet_address)
        if not verified:
            raise HTTPException(
                status_code=402,
                detail=ErrorResponse(
                    error_code="PAYMENT_NOT_VERIFIED",
                    message=f"Could not verify DirectPayment event for your wallet in tx {x_tx_hash}. Ensure you called pay() on contract {settings.contract_address} on BSC and the transaction is confirmed.",
                ).model_dump(),
            )

    elif x_payment_mode == "prepaid":
        # Atomic check-and-deduct in a single SQL UPDATE with WHERE guard.
        # No separate balance check — prevents race condition with concurrent requests.
        consumed = await balance_svc.consume(
            x_wallet_address, settings.payment_amount_wei, endpoint
        )
        if not consumed:
            # First-time user may have deposited on-chain but local DB not yet synced.
            # Sync once and retry before rejecting.
            try:
                await payment_svc.sync_balance(x_wallet_address)
            except Exception:
                pass  # sync failure is non-fatal; we'll check consume again
            consumed = await balance_svc.consume(
                x_wallet_address, settings.payment_amount_wei, endpoint
            )
        payment_svc.invalidate_balance_cache(x_wallet_address)
        if not consumed:
            raise HTTPException(
                status_code=402,
                detail=ErrorResponse(
                    error_code="INSUFFICIENT_BALANCE",
                    message=f"Insufficient prepaid balance. Deposit USDT to contract {settings.contract_address} on BSC (chain ID 56). Each API call costs 0.01 USDT.",
                ).model_dump(),
            )
        # Mark for refund-on-upstream-failure middleware
        request.state.paid_wallet = x_wallet_address
        request.state.paid_amount = settings.payment_amount_wei

    else:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error_code="INVALID_PAYMENT_MODE",
                message="X-Payment-Mode must be 'direct' or 'prepaid'.",
            ).model_dump(),
        )

    return x_wallet_address


async def verify_auth_only(
    x_wallet_address: str = Header(..., alias="X-Wallet-Address"),
    x_signature: str = Header(..., alias="X-Signature"),
    x_message: str = Header(..., alias="X-Message"),
) -> str:
    """Verify authentication signature only (no payment). Used for free authenticated endpoints.

    Returns the wallet address on success.
    """
    if not payment_svc.verify_signature(x_wallet_address, x_message, x_signature):
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error_code="INVALID_SIGNATURE",
                message="Signature verification failed. Sign 'agentcrab:{unix_timestamp}' with your wallet.",
            ).model_dump(),
        )
    return x_wallet_address
